"""Démo exécutable de la boucle Hermes (V2, OPP-060).

Point d'entrée illustratif : monte une base SQLite **en mémoire**, sème un profil
candidat et quelques offres, puis déroule ``HermesOrchestrator.recommend_for_candidate``
et affiche les décisions produites. Déterministe, sans réseau ni LLM — les offres sont
des fixtures directes (l'ingestion LLM relève du pipeline OPP-0392, pas d'Hermes).

Exécution : ``python -m hermes.demo``
"""

from __future__ import annotations

from app.candidate_profile import create_profile
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService

from hermes.models import HermesRecommendation
from hermes.orchestrator import HermesOrchestrator

CANDIDATE_ID = "cand-marie"

# Offres de démonstration : de la plus adaptée au profil à la moins adaptée.
_OFFERS = (
    Offer(
        id="offer-devpy", title="Développeuse Python", company="Acme",
        location="Paris", skills=["Python", "SQL"], seniority="Senior",
        contract_type="CDI", summary="Back-end data", attention_points=[],
        source="indeed", url="https://acme.example/devpy", raw_text="",
    ),
    Offer(
        id="offer-fullstack", title="Ingénieure full-stack", company="Globex",
        location="Paris", skills=["Python", "React"], seniority="Senior",
        contract_type="CDI", summary="Produit web", attention_points=[],
        source="indeed", url="https://globex.example/fullstack", raw_text="",
    ),
    Offer(
        id="offer-javalead", title="Lead Java", company="Initech",
        location="Lyon", skills=["Java"], seniority="Lead",
        contract_type="Freelance", summary="Équipe paiements", attention_points=[],
        source="indeed", url="https://initech.example/javalead", raw_text="",
    ),
)


def run() -> list[HermesRecommendation]:
    """Monte l'environnement en mémoire, sème les fixtures et déroule Hermes."""
    conn = connect(":memory:")
    try:
        profiles = ProfileStore(conn)
        offers = OfferStore(conn)
        decisions = DecisionStore(conn)

        profiles.save(create_profile(
            id=CANDIDATE_ID, name="Marie", skills=["Python", "SQL"],
            contract_type="CDI", location="Paris", total_experience_years=6,
        ))
        for offer in _OFFERS:
            offers.save(offer)

        orchestrator = HermesOrchestrator(
            RecommendationService(profiles, offers),
            DecisionService(decisions),
        )
        return orchestrator.recommend_for_candidate(CANDIDATE_ID)
    finally:
        conn.close()


def render(results: list[HermesRecommendation]) -> str:
    """Rend les résultats Hermes en texte lisible (une décision par offre)."""
    if not results:
        return "Aucune offre évaluable pour ce candidat."
    lines = [f"Décisions Hermes pour {CANDIDATE_ID} — {len(results)} offre(s) :"]
    for rank, result in enumerate(results, start=1):
        offer = result.recommendation.offer
        decision = result.decision
        lines.append(
            f"  {rank}. [{decision.score:>3}/100] {offer.title} @ {offer.company}"
            f" → {decision.action} ({decision.status})"
        )
        lines.append(f"      {decision.justification}")
    return "\n".join(lines)


def main() -> None:
    print(render(run()))


if __name__ == "__main__":
    main()
