"""Intake d'une offre depuis son URL (V2, OPP-148).

Glu « collecte réelle » : fetch de l'URL (``url_fetch``) → extraction du texte
(``html_extract``) → **intake texte existant** (``intake_offer``, OPP-145). Aucune logique
d'analyse neuve : on produit un texte brut à partir d'une page, puis on réutilise la chaîne
analyse LLM → normalisation → persistance déjà testée.

``fetch`` et ``extract`` sont **injectables** (défauts : les implémentations réelles) :
l'intake par URL se teste intégralement sans réseau ni BeautifulSoup réel.
"""

from __future__ import annotations

from typing import Callable

from app.html_extract import extract_offer_text
from app.llm_client import LLMClient
from app.offer import Offer
from app.offer_intake_service import intake_offer
from app.offer_store import OfferRepository
from app.url_fetch import EmptyContentError, HtmlDocument, fetch_html


def intake_offer_from_url(
    url: str,
    *,
    source: str,
    client: LLMClient,
    store: OfferRepository,
    fetch: Callable[[str], HtmlDocument] = fetch_html,
    extract: Callable[[str], str] = extract_offer_text,
) -> Offer:
    """Récupère une offre depuis ``url``, l'analyse et la persiste ; retourne l'``Offer``.

    Propage les erreurs de récupération typées (``UnsupportedUrlError``,
    ``UrlUnreachableError``, ``BlockedError``, ``EmptyContentError``) sans les masquer, puis
    les erreurs d'intake (``ValueError``, ``OfferAnalysisError``, erreurs LLM). Si la page est
    récupérée mais qu'aucun texte exploitable n'en est extrait, lève ``EmptyContentError`` —
    une page vide de contenu est un échec de collecte, pas une offre vide à persister.
    L'URL d'origine est conservée sur l'offre (``offer.url``).
    """
    document = fetch(url)
    text = extract(document.html)
    if text.strip() == "":
        raise EmptyContentError(f"aucun texte exploitable extrait de {url}")
    return intake_offer(text, source=source, client=client, store=store, url=url)
