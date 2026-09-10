"""Tests de la résolution amont run Hermes → (Decision, Offer) (OPP-127).

Vrais dépôts SQLite en mémoire : aucun réseau. On vérifie la reconstitution des couples
(relecture/création de la décision persistée, résolution de l'offre, offre introuvable
tracée), et que le résultat alimente réellement la glu ``submit_pending_reviews``.
"""

import pytest

from app.candidate_profile import create_profile
from app.db import connect
from app.decision import PENDING, create_decision, decision_id, validate
from app.decision_store import DecisionStore
from app.discord_review import DiscordReviewer
from app.llm_client import MockLLMClient
from app.offer import Offer
from app.offer_store import OfferStore
from app.redacteur import LLMRedacteur
from app.review_pipeline import submit_pending_reviews
from app.discord_transport import MockDiscordTransport

from hermes.models import HermesRun, OfferEvaluation
from hermes.review_resolution import ResolvedRun, resolve_run_review_items

CLOCK = "2026-09-09T00:00:00+00:00"


def _offer(offer_id: str, **overrides) -> Offer:
    data = dict(
        id=offer_id, title="Offre", company="Acme", location="Paris",
        skills=["Python"], seniority="Senior", contract_type="CDI",
        summary="s", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    data.update(overrides)
    return Offer(**data)


def _evaluation(offer_id: str, *, action="postuler", score=82) -> OfferEvaluation:
    return OfferEvaluation(
        offer_id=offer_id, score=score, action=action,
        title="Offre", company="Acme", justification="Bon match",
    )


def _run(*evaluations: OfferEvaluation, candidate_id="cand-1") -> HermesRun:
    return HermesRun(
        run_id="run-1", candidate_id=candidate_id, executed_at=CLOCK,
        evaluations=tuple(evaluations),
    )


@pytest.fixture
def stores():
    conn = connect(":memory:")
    yield OfferStore(conn), DecisionStore(conn)
    conn.close()


# --- résolution nominale ------------------------------------------------------


def test_resolves_couples_in_run_order(stores):
    offers, decisions = stores
    offers.save(_offer("a"))
    offers.save(_offer("b"))
    run = _run(_evaluation("a"), _evaluation("b"))

    resolved = resolve_run_review_items(run, decisions=decisions, offers=offers)

    assert isinstance(resolved, ResolvedRun)
    assert [offer.id for _, offer in resolved.items] == ["a", "b"]
    assert resolved.missing_offers == ()
    # Garde-fou identifiants : décision et offre partagent le même offer_id.
    for decision, offer in resolved.items:
        assert decision.offer_id == offer.id


def test_relit_la_decision_persistee_avec_validation_humaine(stores):
    offers, decisions = stores
    offers.save(_offer("a"))
    # Une décision déjà tranchée par un humain (approved) est persistée.
    persisted = validate(
        create_decision(
            candidate_id="cand-1", offer_id="a", action="postuler",
            score=82, justification="Bon match", now=lambda: CLOCK,
        ),
        "approved", now=lambda: CLOCK,
    )
    decisions.save(persisted)

    resolved = resolve_run_review_items(_run(_evaluation("a")), decisions=decisions, offers=offers)

    decision, _ = resolved.items[0]
    # C'est bien la décision courante (approved) qui est relue, pas une recréation pending.
    assert decision.status == "approved"
    assert decision == persisted


def test_recree_et_persiste_la_decision_absente_depuis_le_snapshot(stores):
    offers, decisions = stores
    offers.save(_offer("a"))
    run = _run(_evaluation("a", action="postuler", score=77))
    assert decisions.count() == 0  # aucune décision préexistante

    resolved = resolve_run_review_items(
        run, decisions=decisions, offers=offers, now=lambda: CLOCK
    )

    decision, _ = resolved.items[0]
    # Recréée à l'identique du snapshot figé, au statut pending, et persistée.
    assert decision.status == PENDING
    assert (decision.action, decision.score, decision.justification) == (
        "postuler", 77, "Bon match",
    )
    stored = decisions.get(decision_id("cand-1", "a"))
    assert stored == decision
    assert stored.history[0].at == CLOCK  # horloge injectée respectée


def test_offre_introuvable_est_tracee_pas_fatale(stores):
    offers, decisions = stores
    offers.save(_offer("a"))
    offers.save(_offer("c"))
    # 'b' n'existe pas dans le store : elle doit être tracée et sautée, sans casser le lot.
    run = _run(_evaluation("a"), _evaluation("b"), _evaluation("c"))

    resolved = resolve_run_review_items(run, decisions=decisions, offers=offers)

    assert [offer.id for _, offer in resolved.items] == ["a", "c"]  # ordre préservé
    assert resolved.missing_offers == ("b",)
    # Aucune décision recréée pour l'offre introuvable.
    assert decisions.get(decision_id("cand-1", "b")) is None


def test_run_vide_donne_un_resultat_vide(stores):
    offers, decisions = stores
    resolved = resolve_run_review_items(_run(), decisions=decisions, offers=offers)
    assert resolved.items == []
    assert resolved.missing_offers == ()


def test_offer_id_duplique_resolu_une_seule_fois(stores):
    offers, decisions = stores
    offers.save(_offer("a"))
    offers.save(_offer("b"))
    # Deux évaluations sur 'a' : un seul couple doit sortir, pour ne pas pousser deux fois.
    run = _run(_evaluation("a"), _evaluation("b"), _evaluation("a", score=90))

    resolved = resolve_run_review_items(run, decisions=decisions, offers=offers)

    assert [offer.id for _, offer in resolved.items] == ["a", "b"]  # 'a' dédoublonnée
    # La première occurrence prime (snapshot figé) : le score 90 du doublon est ignoré.
    decision_a, _ = resolved.items[0]
    assert decision_a.score == 82


def test_offer_id_manquant_duplique_trace_une_seule_fois(stores):
    offers, decisions = stores
    # 'b' introuvable, présente deux fois : tracée une seule fois dans missing_offers.
    run = _run(_evaluation("b"), _evaluation("b"))

    resolved = resolve_run_review_items(run, decisions=decisions, offers=offers)

    assert resolved.items == []
    assert resolved.missing_offers == ("b",)


def test_run_pre_opp095_sans_action_est_resolu_sans_filtrer(stores):
    offers, decisions = stores
    offers.save(_offer("a"))
    # Run antérieur à OPP-095 : l'action auto n'a pas été figée (action="").
    run = _run(_evaluation("a", action=""))

    resolved = resolve_run_review_items(
        run, decisions=decisions, offers=offers, now=lambda: CLOCK
    )

    # Le module résout sans éditorialiser : le couple sort, action="" fidèle au snapshot.
    decision, offer = resolved.items[0]
    assert offer.id == "a"
    assert decision.action == ""
    # Le tri des dossiers éligibles reste au ressort de la glu (défaut : postuler+pending),
    # qui écartera d'elle-même une action vide — ce module ne filtre pas.


# --- intégration avec la glu (OPP-123) ---------------------------------------


def test_items_alimentent_submit_pending_reviews(stores):
    offers, decisions = stores
    offers.save(_offer("a"))
    offers.save(_offer("b"))
    offers.save(_offer("c"))
    # 'a' à candidater et 'b' à étudier sont poussées (OPP-141) ; 'c' à ignorer est filtrée.
    run = _run(
        _evaluation("a", action="postuler"),
        _evaluation("b", action="a_etudier"),
        _evaluation("c", action="ignorer"),
    )

    resolved = resolve_run_review_items(run, decisions=decisions, offers=offers)

    transport = MockDiscordTransport()
    results = submit_pending_reviews(
        resolved.items,
        create_profile(name="Marie", skills=["Python"], contract_type="CDI"),
        redacteur=LLMRedacteur(
            MockLLMClient(["Madame, Monsieur, " + "motivation " * 20] * 2)
        ),
        reviewer=DiscordReviewer(transport, channel_id="chan-1"),
    )

    assert [r.recommendation_id for r in results] == [
        decision_id("cand-1", "a"),
        decision_id("cand-1", "b"),
    ]
    assert len(transport.sent) == 2  # 'c' (ignorer) reste hors revue
