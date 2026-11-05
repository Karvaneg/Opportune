"""Candidat de démonstration — seed d'une boucle complète (V2, OPP-180).

Pose en base un **candidat de démo séparé** (``cand-demo``), distinct du candidat de prod :
profil réaliste (compétences + parcours), offres variées, décisions humaines et candidature,
et une lettre de motivation. De quoi présenter Opportune « vivant » à un tiers, se faire un bac
à sable de test, ou offrir un exemple d'onboarding — les trois usages d'un même seed.

**Sans réseau ni LLM** : le scoring est déterministe (``RecommendationService``) et la lettre est
pré-rédigée. **Convergent / idempotent** : chaque pièce est un upsert (profil, offres, décisions,
lettre) et la candidature passe par ``ActionService`` (idempotent par nature). Relancer le seed
restaure donc l'état canonique du candidat démo — pas de doublon, pas d'historique qui gonfle —
ce qui tient lieu de « réinitialisation » sans suppression destructive.

La logique vit ici (couche ``app``) pour être partagée par le **CLI** (``hermes.seed_demo_candidate``)
et l'**API** (bouton « Créer un profil de démo »). Elle ne câble que des briques existantes.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.action_service import ActionService
from app.action_store import ApplicationActionStore, OutboundMessageActionStore
from app.candidate_registry import CandidateRegistry
from app.candidate_profile import create_profile
from app.decision import decision_from_recommendation, decision_id, validate
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.letter import SOURCE_AI, Letter
from app.letter_store import LetterStore
from app.offer import Offer, compute_offer_id
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.models import HermesRun, OfferEvaluation
from hermes.run_store import RunStore

# Identité du candidat démo — un id dédié, jamais celui d'une vraie recherche. Vit dans l'espace
# démo isolé (base séparée), semé au premier lancement (cf. ``api.server``).
DEMO_CANDIDATE_ID = "cand-demo"
DEMO_CANDIDATE_NAME = "Alex Démo"

# Id **fixe** du run de démo : à id constant, re-seeder upsert le même run (convergent) au lieu
# d'en empiler un par re-seed. Le run figure une analyse déjà passée (Historique peuplé) et coche
# l'étape « Lancer une analyse » du guide d'accueil — la vitrine montre une boucle complète.
DEMO_RUN_ID = "demo-run"

# Provenance des offres de démo (champ ``source``) : les distingue des vraies offres collectées.
DEMO_SOURCE = "demo"


def _demo_profile_kwargs() -> dict:
    """Profil démo canonique : un·e dev fullstack fictif·ve mais crédible."""
    return dict(
        id=DEMO_CANDIDATE_ID,
        name=DEMO_CANDIDATE_NAME,
        skills=["Python", "SQL", "React", "Docker", "Git", "FastAPI", "PostgreSQL"],
        contract_type="CDI",
        location="Bordeaux",
        total_experience_years=6,
        languages=["Français", "Anglais"],
        experiences=[
            {
                "title": "Développeuse back-end",
                "company": "Lumen Data",
                "period": "2022 – 2025",
                "location": "Bordeaux",
                "highlights": [
                    "Conception d'APIs Python/FastAPI pour une plateforme data",
                    "Migration d'un monolithe vers des services conteneurisés (Docker)",
                ],
                "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            },
            {
                "title": "Développeuse full-stack",
                "company": "Nova Studio",
                "period": "2019 – 2022",
                "location": "Toulouse",
                "highlights": [
                    "Développement d'un produit web React + API Python",
                    "Mise en place de l'intégration continue et des tests",
                ],
                "skills": ["React", "Python", "SQL", "Git"],
            },
        ],
    )


def _demo_offer(*, slug: str, title: str, **fields) -> Offer:
    """Construit une offre démo avec un id **adressé par contenu** (``compute_offer_id``).

    L'id doit être **exactement** celui que dérive ``OfferStore`` (de ``source`` + ``url``) :
    sa migration d'identité (OPP-119) recalcule l'id de chaque offre à l'ouverture et réécrit la
    clé si elle diffère. Un id arbitraire (``demo-py-senior``) serait donc réécrit en hash à la
    première réouverture, alors que les décisions du scénario — qui référencent cet id — ne le
    seraient pas : l'entonnoir du cockpit ne retrouverait plus ses offres. On aligne donc l'id
    sur le schéma du store dès le seed. ``url`` (stable, unique par offre) sert de discriminant.
    """
    url = f"https://example.com/demo/{slug}"
    raw_text = f"Offre de démonstration — {title}."
    return Offer(
        id=compute_offer_id(DEMO_SOURCE, url, raw_text),
        title=title,
        source=DEMO_SOURCE,
        url=url,
        raw_text=raw_text,
        **fields,
    )


# Offres de démo (clé logique → offre), de la plus pertinente à la moins. La clé logique sert le
# scénario ci-dessous ; l'id réel est adressé par contenu (cf. ``_demo_offer``).
_DEMO_OFFERS: dict[str, Offer] = {
    "py-senior": _demo_offer(
        slug="py-senior",
        title="Développeuse Python Senior",
        company="Lumen Tech",
        location="Bordeaux",
        skills=["Python", "SQL", "Docker", "FastAPI"],
        seniority="Senior",
        contract_type="CDI",
        summary="Back-end data : APIs Python, SQL, conteneurisation.",
        attention_points=[],
    ),
    "fullstack": _demo_offer(
        slug="fullstack",
        title="Ingénieure full-stack",
        company="Nova Web",
        location="Bordeaux",
        skills=["Python", "React", "SQL"],
        seniority="Confirmé",
        contract_type="CDI",
        summary="Produit web : React en front, API Python en back.",
        attention_points=[],
    ),
    "backend": _demo_offer(
        slug="backend",
        title="Développeur back-end",
        company="DataForge",
        location="Paris",
        skills=["Python", "SQL"],
        seniority="Confirmé",
        contract_type="CDI",
        summary="Services back-end data en Python.",
        attention_points=[],
    ),
    "data-eng": _demo_offer(
        slug="data-eng",
        title="Data Engineer",
        company="FluxData",
        location="Lyon",
        skills=["Python", "SQL", "Spark"],
        seniority="Confirmé",
        contract_type="CDI",
        summary="Pipelines de données, Python et Spark.",
        attention_points=["Spark non maîtrisé"],
    ),
    "lead-java": _demo_offer(
        slug="lead-java",
        title="Lead Java",
        company="Banque Centrale",
        location="Paris",
        skills=["Java", "Spring"],
        seniority="Lead",
        contract_type="freelance",
        summary="Équipe paiements, stack Java/Spring.",
        attention_points=["Stack éloignée du profil"],
    ),
}


def _demo_offers() -> list[Offer]:
    """Les cinq offres de démo, de la plus pertinente à la moins."""
    return list(_DEMO_OFFERS.values())


# Lettre de motivation pré-rédigée (sans LLM) pour l'offre candidatée du scénario.
_DEMO_LETTER_BODY = (
    "Madame, Monsieur,\n\n"
    "Développeuse back-end avec six ans d'expérience en Python, SQL et conteneurisation, "
    "je suis vivement intéressée par le poste de Développeuse Python Senior chez Lumen Tech. "
    "Mon parcours chez Lumen Data m'a permis de concevoir des APIs performantes et de mener "
    "une migration vers des services conteneurisés — des compétences directement alignées avec "
    "vos enjeux.\n\n"
    "Je serais ravie d'échanger sur votre projet et la façon dont je peux y contribuer.\n\n"
    "Cordialement,\nAlex Démo"
)


@dataclass(frozen=True)
class _Step:
    """Une étape du scénario : l'offre, la décision humaine à poser, la candidature, la lettre."""

    offer_id: str
    decision: str | None  # None → laissée « à étudier » ; "approved" ; "rejected"
    applied: bool = False
    letter: str | None = None


# Scénario de démo : remplit l'entonnoir du cockpit (à étudier / à postuler / postulé) et montre
# une offre écartée. L'étape « postulé » porte aussi la lettre.
_SCENARIO: tuple[_Step, ...] = (
    _Step(_DEMO_OFFERS["py-senior"].id, decision="approved", applied=True, letter=_DEMO_LETTER_BODY),
    _Step(_DEMO_OFFERS["fullstack"].id, decision="approved"),
    _Step(_DEMO_OFFERS["backend"].id, decision=None),
    _Step(_DEMO_OFFERS["data-eng"].id, decision=None),
    _Step(_DEMO_OFFERS["lead-java"].id, decision="rejected"),
)


@dataclass(frozen=True)
class DemoSeedSummary:
    """Bilan du seed, pour le retour CLI/API."""

    candidate_id: str
    offers: int
    decisions: int
    applied: int
    letters: int


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_demo_candidate(
    conn: sqlite3.Connection,
    *,
    now: Callable[[], str] | None = None,
    new_id: Callable[[], str] | None = None,
) -> DemoSeedSummary:
    """Pose (ou restaure) le candidat démo complet sur la connexion donnée.

    Câble les mêmes dépôts que l'API (cf. ``api.server``) puis déroule le scénario :
    profil → offres → scoring déterministe → décisions humaines → candidature → lettre.
    Convergent : relancer restaure l'état canonique sans doublon. ``now``/``new_id`` sont
    injectables pour des dates et identifiants déterministes en test.
    """
    clock = now or _utcnow_iso
    mint_id = new_id or (lambda: uuid.uuid4().hex)

    profiles = ProfileStore(conn)
    offers = OfferStore(conn)
    decision_store = DecisionStore(conn)
    decisions = DecisionService(decision_store, now=clock)
    actions = ActionService(
        decisions,
        ApplicationActionStore(conn),
        OutboundMessageActionStore(conn),
        new_id=mint_id,
        now=clock,
    )
    letters = LetterStore(conn)
    runs = RunStore(conn)
    recommender = RecommendationService(profiles, offers)

    # 0. Périmètre : le candidat démo est enrôlé dans le registre (OPP-183) — son slot existe
    #    indépendamment du profil (il survit à un « repartir de zéro », cf. ``reset_demo``).
    CandidateRegistry(conn).add(DEMO_CANDIDATE_ID, label=DEMO_CANDIDATE_NAME)

    # 1. Profil démo (upsert : écrase toujours vers le profil canonique — 100 % synthétique).
    profiles.save(create_profile(**_demo_profile_kwargs()))

    # 2. Offres (upsert sur id stable).
    for offer in _demo_offers():
        offers.save(offer)

    # 3. Scoring + décisions + candidature + lettre, selon le scénario.
    evaluations: list[OfferEvaluation] = []
    n_decisions = n_applied = n_letters = 0
    for step in _SCENARIO:
        recommendation = recommender.recommend_one(DEMO_CANDIDATE_ID, step.offer_id)
        if recommendation is None:
            continue  # offre non évaluable : on ne fabrique pas de décision creuse
        # Décision construite via les fonctions pures puis sauvée (upsert) : historique fixe,
        # donc convergent au re-seed (contrairement à un validate() répété qui l'allongerait).
        decision = decision_from_recommendation(recommendation, DEMO_CANDIDATE_ID, now=clock)
        # Snapshot d'analyse figé **avant** toute validation humaine (comme un vrai run) : le
        # statut de décision au run-time est donc l'avis automatique, pas encore tranché.
        evaluations.append(
            OfferEvaluation(
                offer_id=step.offer_id,
                score=recommendation.score,
                decision_status=decision.status,
                advisory_status=decision.status,
                action=recommendation.action,
                title=recommendation.offer.title,
                company=recommendation.offer.company,
                justification=recommendation.justification,
            )
        )
        if step.decision is not None:
            decision = validate(decision, step.decision, comment="Décision de démo", now=clock)
        decision_store.save(decision)
        n_decisions += 1

        recommendation_id = decision_id(DEMO_CANDIDATE_ID, step.offer_id)
        if step.applied:
            # Exige une décision ``approved`` en base (vient d'être sauvée) : l'intention puis la
            # candidature passent par ActionService, idempotent (pas de doublon au re-seed).
            actions.confirm_application(recommendation_id)
            actions.mark_applied(recommendation_id)
            n_applied += 1

        if step.letter is not None:
            stamp = clock()
            letters.save(
                Letter(
                    recommendation_id=recommendation_id,
                    body=step.letter,
                    source=SOURCE_AI,
                    model="demo",
                    created_at=stamp,
                    updated_at=stamp,
                )
            )
            n_letters += 1

    # 4. Run d'analyse à id fixe (convergent) : peuple l'Historique et coche l'étape « Lancer
    #    une analyse » du guide d'accueil, pour que la vitrine présente une boucle complète.
    if evaluations:
        runs.save(
            HermesRun(
                run_id=DEMO_RUN_ID,
                candidate_id=DEMO_CANDIDATE_ID,
                executed_at=clock(),
                evaluations=tuple(evaluations),
            )
        )

    return DemoSeedSummary(
        candidate_id=DEMO_CANDIDATE_ID,
        offers=len(_demo_offers()),
        decisions=n_decisions,
        applied=n_applied,
        letters=n_letters,
    )


def reset_demo(conn: sqlite3.Connection) -> None:
    """Vide **toutes** les données de la base démo — bac à sable repartant de zéro (OPP-182).

    « Repartir de zéro » : on supprime le contenu de chaque table métier (profil, offres,
    décisions, candidatures, messages, lettres, runs…) sans toucher au schéma, pour que
    l'utilisateur refasse le parcours à la main dans cet espace isolé. On énumère les tables
    plutôt que de les lister en dur : la base démo n'héberge **que** des données de démo, donc
    un vidage total est sûr et ne peut jamais rater une table (ni, par construction du routeur,
    atteindre la base réelle). ``restore`` = ``reset_demo`` puis ``seed_demo_candidate``.

    Table rase **complète** : le registre des recherches est vidé lui aussi, candidat démo
    compris (OPP-195). Le périmètre devient vide → le sélecteur invite à **créer une nouvelle
    recherche**, au lieu de laisser une « Alex Demo » sans données (dont le profil répondrait 404).
    « Restaurer l'exemple » (``reset_demo`` puis ``seed_demo_candidate``) réinsère le slot et la
    vitrine canonique.
    """
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    for table in tables:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
