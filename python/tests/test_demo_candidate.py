"""Tests du candidat de démonstration (OPP-180).

SQLite en mémoire, aucun réseau ni LLM. On vérifie que le seed pose une boucle complète et
cohérente (profil, offres, entonnoir du cockpit, candidature, lettre), et qu'il est convergent
(rejouable sans doublon ni historique qui gonfle).
"""

import pytest

from app.action_store import ApplicationActionStore
from app.candidate_registry import CandidateRegistry
from app.db import connect
from app.decision import decision_id
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.demo_candidate import (
    DEMO_CANDIDATE_ID,
    DEMO_CANDIDATE_NAME,
    _DEMO_OFFERS,
    migrate_demo_search_label,
    reset_demo,
    seed_demo_candidate,
)
from app.letter_store import LetterStore
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore

from app.demo_candidate import DEMO_RUN_ID

FIXED_NOW = "2026-10-23T10:00:00+00:00"

# Id (adressé par contenu) de l'offre candidatée du scénario — sert aux lookups lettre/décision.
PY_SENIOR_ID = _DEMO_OFFERS["py-senior"].id


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def _counter_ids():
    """Fabrique d'ids déterministe (``id-0``, ``id-1``, …) pour des tests reproductibles."""
    n = 0

    def mint() -> str:
        nonlocal n
        value = f"id-{n}"
        n += 1
        return value

    return mint


def _seed(conn):
    return seed_demo_candidate(conn, now=lambda: FIXED_NOW, new_id=_counter_ids())


def _funnel(conn):
    """Entonnoir du cockpit **via le chemin réel de l'API** (orchestrateur).

    On ne reconstruit pas l'entonnoir « à la main » : on passe par ``candidate_stats`` comme
    l'endpoint ``/stats``. C'est ce qui garantit que l'id des décisions coïncide avec l'id des
    offres **tel que le store le liste** (``offer_ids``) — une reconstruction par ``decision_id``
    masquerait une divergence d'id (cf. migration d'identité d'offre, OPP-119).
    """
    applied = ApplicationActionStore(conn).applied_recommendation_ids(DEMO_CANDIDATE_ID)
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return orchestrator.candidate_stats(DEMO_CANDIDATE_ID, applied_recommendation_ids=applied)


def test_seed_pose_profil_offres_et_lettre(conn):
    summary = _seed(conn)

    profile = ProfileStore(conn).get(DEMO_CANDIDATE_ID)
    assert profile is not None
    assert "Python" in profile.skills
    assert len(profile.experiences) == 2  # parcours visible dans l'UI
    assert OfferStore(conn).count() == 5
    assert summary.offers == 5

    # Lettre pré-rédigée posée sur l'offre candidatée.
    letter = LetterStore(conn).get(decision_id(DEMO_CANDIDATE_ID, PY_SENIOR_ID))
    assert letter is not None
    assert letter.source == "ai"
    assert "Lumen Tech" in letter.body


def test_seed_remplit_l_entonnoir_du_cockpit(conn):
    _seed(conn)

    stats = _funnel(conn)
    # 1 postulé (py-senior), 1 à postuler (fullstack), 2 à étudier (backend, data-eng),
    # lead-java rejeté → hors entonnoir mais compté dans le total.
    assert (stats.a_etudier, stats.a_postuler, stats.postule) == (2, 1, 1)
    assert stats.offres_total == 5


def test_seed_est_convergent_au_rejeu(conn):
    _seed(conn)
    _seed(conn)  # rejoué

    # Pas de doublon d'offre ni de candidature ; l'entonnoir reste identique.
    assert OfferStore(conn).count() == 5
    assert ApplicationActionStore(conn).count() == 1
    stats = _funnel(conn)
    assert (stats.a_etudier, stats.a_postuler, stats.postule) == (2, 1, 1)

    # L'historique de décision ne gonfle pas : pending + approved = 2 événements, pas davantage.
    approved = DecisionStore(conn).get(decision_id(DEMO_CANDIDATE_ID, PY_SENIOR_ID))
    assert approved is not None
    assert approved.status == "approved"
    assert len(approved.history) == 2


def test_seed_pose_un_run_convergent(conn):
    # La vitrine montre une analyse déjà passée (Historique peuplé) → l'étape « Lancer une
    # analyse » du guide se coche. À id fixe, re-seeder n'empile pas les runs.
    _seed(conn)
    _, total = RunStore(conn).list_run_summaries([DEMO_CANDIDATE_ID], limit=10, offset=0)
    assert total == 1

    _seed(conn)  # rejoué
    summaries, total = RunStore(conn).list_run_summaries([DEMO_CANDIDATE_ID], limit=10, offset=0)
    assert total == 1
    assert summaries[0].run_id == DEMO_RUN_ID


def test_reset_demo_vide_tout(conn):
    _seed(conn)
    assert OfferStore(conn).count() == 5
    assert ProfileStore(conn).get(DEMO_CANDIDATE_ID) is not None

    reset_demo(conn)

    # Bac à sable repartant de zéro : plus d'offre, plus de profil, plus de décision.
    assert OfferStore(conn).count() == 0
    assert ProfileStore(conn).get(DEMO_CANDIDATE_ID) is None
    assert DecisionStore(conn).count() == 0

    # Table rase complète (OPP-195) : le slot du candidat démo est vidé lui aussi → périmètre
    # vide, le sélecteur invite à créer une nouvelle recherche (plus de recherche démo résiduelle).
    assert CandidateRegistry(conn).list_ids() == []

    # « Restaurer l'exemple » (reset + seed) ramène le slot et la vitrine canonique.
    reset_demo(conn)
    seed_demo_candidate(conn)
    assert OfferStore(conn).count() == 5
    assert CandidateRegistry(conn).list_ids() == [DEMO_CANDIDATE_ID]


def test_seed_links_every_demo_offer_to_the_demo_search(conn):
    # OPP-186 : les offres de la vitrine sont celles de la recherche démo, y compris après un
    # « Restaurer l'exemple » (vidage puis re-seed, la table de liens existant déjà).
    from app.candidate_offer_store import CandidateOfferStore

    _seed(conn)
    reset_demo(conn)
    _seed(conn)

    linked = CandidateOfferStore(conn).offer_ids(DEMO_CANDIDATE_ID)

    assert sorted(linked) == sorted(offer.id for offer in _DEMO_OFFERS.values())


def _demo_search_label(conn) -> str:
    return next(s.label for s in CandidateRegistry(conn).list() if s.id == DEMO_CANDIDATE_ID)


def test_seed_names_the_demo_search_after_the_job_not_the_person(conn):
    # OPP-245 : la recherche porte le nom du poste ; le profil garde le nom de la personne.
    _seed(conn)

    assert _demo_search_label(conn) == "Dev Python"
    assert ProfileStore(conn).get(DEMO_CANDIDATE_ID).name == DEMO_CANDIDATE_NAME


def test_migrate_renames_a_demo_search_still_labelled_with_the_old_default(conn):
    # Base démo créée avant OPP-245 : le seed avait posé « Alex Démo » comme libellé.
    _seed(conn)
    CandidateRegistry(conn).rename(DEMO_CANDIDATE_ID, "Alex Démo")

    migrate_demo_search_label(conn)

    assert _demo_search_label(conn) == "Dev Python"


def test_migrate_keeps_a_demo_search_label_given_by_hand(conn):
    _seed(conn)
    CandidateRegistry(conn).rename(DEMO_CANDIDATE_ID, "Mon test")

    migrate_demo_search_label(conn)

    assert _demo_search_label(conn) == "Mon test"


def test_migrate_does_not_recreate_the_demo_search_after_a_reset(conn):
    # « Repartir de zéro » vide le registre : la migration ne doit pas ressusciter la recherche.
    _seed(conn)
    reset_demo(conn)

    migrate_demo_search_label(conn)

    assert CandidateRegistry(conn).list_ids() == []
