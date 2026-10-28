"""Intégration de l'analyse LLM dans le cycle d'une offre (V2, OPP-037).

Orchestration de bout en bout :

    texte brut → analyse LLM → validation → normalisation → Offer → persistance

Ne dépend que de contrats injectables : ``LLMClient`` (OPP-079) pour l'analyse et
``OfferRepository`` (OPP-037) pour le stockage — d'où une testabilité complète avec un
faux LLM et une fausse persistance, sans réseau ni SQLite réel.

**Enrichissement en secours (OPP-169).** ``intake_offer_enriched`` attaque la cause des
offres sans compétences : certaines sources (ex. Adzuna) ne fournissent qu'un **extrait
tronqué** de l'annonce, trop maigre pour que le LLM en extraie des compétences. Quand
l'analyse ne sort **aucune** compétence et qu'une URL est disponible, on récupère la page
complète (chaîne OPP-148 : ``url_fetch`` → ``html_extract``) et on ré-analyse ce texte plus
riche. L'enrichissement est un **bonus** : tout échec (site anti-bot, page injoignable ou
vide, ré-analyse non conforme) retombe silencieusement sur l'analyse initiale — il ne doit
jamais retirer une offre du catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from app.html_extract import extract_offer_text
from app.llm_client import LLMClient, LLMError
from app.offer import Offer
from app.offer_analysis import OfferAnalysis, OfferAnalysisError
from app.offer_analysis_service import analyze_offer
from app.offer_normalization import drop_unanchored_skills
from app.offer_store import OfferRepository
from app.url_fetch import HtmlDocument, UrlFetchError, fetch_html


@dataclass(frozen=True)
class IntakeResult:
    """Résultat d'un intake enrichi : l'offre + ce que l'enrichissement a fait (OPP-169).

    ``enrichment_attempted`` : l'analyse initiale n'a laissé aucune compétence **ancrée** au
    texte (OPP-213) et une URL était disponible → la page complète a été récupérée et ré-analysée.
    ``enrichment_recovered`` : parmi ces tentatives, l'offre a **effectivement** gagné des
    compétences après ré-analyse. Ces drapeaux alimentent les compteurs du bilan de collecte.
    """

    offer: Offer
    enrichment_attempted: bool = False
    enrichment_recovered: bool = False


def _build_offer(
    analysis: OfferAnalysis, *, source: str, url: str, raw_text: str
) -> Offer:
    """Normalise une analyse en ``Offer`` et **ancre** ses skills au texte (sans persister).

    L'ancrage (``drop_unanchored_skills``, OPP-213) s'applique ici — en aval de la
    normalisation d'une collecte réelle — plutôt que dans ``Offer.from_analysis`` : on garde
    intact le contrat de normalisation pure du modèle. Le filtre porte sur les skills **déjà
    atomisées/normalisées** par ``from_analysis``, et compare au ``raw_text`` effectivement
    analysé (extrait de source ou page complète récupérée). La construction est pure (aucune
    I/O) : ``intake_offer_enriched`` s'en sert pour décider de l'enrichissement sur les skills
    **réellement ancrés**, et non sur les skills bruts (potentiellement inventés) du modèle.
    """
    offer = Offer.from_analysis(analysis, source=source, url=url, raw_text=raw_text)
    return replace(offer, skills=drop_unanchored_skills(offer.skills, raw_text))


def _persist(
    analysis: OfferAnalysis, *, source: str, url: str, raw_text: str, store: OfferRepository
) -> Offer:
    """Construit l'``Offer`` ancrée (cf. ``_build_offer``) et la persiste ; retourne l'offre."""
    offer = _build_offer(analysis, source=source, url=url, raw_text=raw_text)
    store.save(offer)
    return offer


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
    return _persist(
        analyze_offer(raw_text, client), source=source, url=url, raw_text=raw_text, store=store
    )


def intake_offer_enriched(
    raw_text: str,
    *,
    source: str,
    client: LLMClient,
    store: OfferRepository,
    url: str = "",
    fetch: Callable[[str], HtmlDocument] = fetch_html,
    extract: Callable[[str], str] = extract_offer_text,
) -> IntakeResult:
    """Intake avec **enrichissement en secours** (OPP-169) ; retourne un ``IntakeResult``.

    Analyse d'abord ``raw_text`` tel quel (cas courant : une seule passe). Si cette analyse
    ne produit **aucune** compétence et qu'une ``url`` est fournie, récupère la page complète
    et ré-analyse ce texte. L'enrichissement est opportuniste : tout échec de récupération
    (``UrlFetchError``) ou de ré-analyse (``OfferAnalysisError``/``LLMError``) retombe sur
    l'analyse du texte initial — le catalogue ne rétrécit jamais à cause de l'enrichissement.

    ``fetch`` et ``extract`` sont injectables (défauts : implémentations réelles) pour un
    test sans réseau. Comme l'id d'offre repose sur l'URL canonicalisée quand elle existe
    (``compute_offer_id``), remplacer le texte analysé **ne change pas** l'identité de l'offre.
    """
    analysis = analyze_offer(raw_text, client)
    offer = _build_offer(analysis, source=source, url=url, raw_text=raw_text)
    attempted = False
    # Décision d'enrichissement fondée sur les skills **ancrés** (OPP-213) : un snippet dont
    # toutes les compétences extraites sont inventées/reformulées (donc écartées par l'ancrage)
    # finit sans skill ancrée → on récupère la page complète exactement comme pour une analyse
    # qui n'aurait sorti aucune compétence, au lieu de persister une offre silencieusement vidée.
    if not offer.skills and url:
        attempted = True
        enriched = _fetch_offer_text(url, fetch, extract)
        if enriched is not None:
            try:
                analysis = analyze_offer(enriched, client)
                offer = _build_offer(analysis, source=source, url=url, raw_text=enriched)
            except (OfferAnalysisError, LLMError):
                pass  # ré-analyse infructueuse : on garde l'offre issue du texte initial
    store.save(offer)
    # « Récupéré » = la tentative a réellement abouti à des compétences (et non snippet vide,
    # fetch bloqué ou ré-analyse toujours sans compétence ancrée).
    return IntakeResult(
        offer=offer,
        enrichment_attempted=attempted,
        enrichment_recovered=attempted and bool(offer.skills),
    )


def _fetch_offer_text(
    url: str, fetch: Callable[[str], HtmlDocument], extract: Callable[[str], str]
) -> str | None:
    """Récupère et extrait le texte de la page ``url`` ; ``None`` si rien d'exploitable.

    Tout échec de récupération (``UrlFetchError`` : schéma refusé, anti-bot, injoignable,
    page vide) est absorbé en ``None`` — l'appelant retombe alors sur le texte d'origine.
    ``RuntimeError`` l'est aussi : ``extract_offer_text`` le lève quand l'extra ``scrape``
    (BeautifulSoup) est absent. L'enrichissement étant un bonus opportuniste (cf. docstring
    du module), une dépendance optionnelle manquante ne doit pas faire tomber la passe.
    """
    try:
        document = fetch(url)
        text = extract(document.html)
    except (UrlFetchError, RuntimeError):
        return None
    text = text.strip()
    return text or None
