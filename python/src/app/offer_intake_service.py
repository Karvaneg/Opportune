"""Intégration de l'analyse LLM dans le cycle d'une offre (V2, OPP-037).

Orchestration de bout en bout :

    texte brut → analyse LLM → validation → normalisation → Offer → persistance

Ne dépend que de contrats injectables : ``LLMClient`` (OPP-079) pour l'analyse et
``OfferRepository`` (OPP-037) pour le stockage — d'où une testabilité complète avec un
faux LLM et une fausse persistance, sans réseau ni SQLite réel.
"""

from __future__ import annotations

from app.llm_client import LLMClient
from app.offer import Offer
from app.offer_analysis_service import analyze_offer
from app.offer_store import OfferRepository


def intake_offer(
    raw_text: str,
    *,
    source: str,
    client: LLMClient,
    store: OfferRepository,
    url: str = "",
) -> Offer:
    """Analyse, normalise et persiste une offre brute ; retourne l'``Offer``.

    Propage ``ValueError`` (texte/source vide), ``OfferAnalysisError`` (analyse LLM
    non conforme) et les erreurs du client LLM. En cas d'échec avant ``save``, rien
    n'est persisté.
    """
    analysis = analyze_offer(raw_text, client)
    offer = Offer.from_analysis(analysis, source=source, url=url, raw_text=raw_text)
    store.save(offer)
    return offer
