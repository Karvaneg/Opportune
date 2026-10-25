"""Pipeline générique de collecte d'offres (V2, OPP-119).

Le **socle** de la collecte réelle, derrière le port ``SourceOffres`` : il enchaîne

    collecte (source) → dédoublonnage → analyse/normalisation → persistance

sans rien connaître d'une source concrète ni réintroduire de logique d'analyse (il
réutilise ``intake_offer``, donc la chaîne analyse LLM → normalisation → ``Offer`` →
``OfferStore`` déjà testée).

**Dédoublonnage avant analyse.** La clé est l'id stable ``compute_offer_id`` calculé sur
la ``RawOffer`` *brute* — exactement l'id que produira la persistance en aval. Une offre
déjà connue (présente dans le dépôt, ou déjà vue plus tôt dans la même passe) est donc
écartée **sans appeler le LLM** : en collecte de masse, l'analyse — l'étape coûteuse — ne
tourne que pour les offres neuves. L'URL étant canonicalisée dans la clé, « même offre,
deux liens de tracking » dédoublonne aussi (OPP-119).

**Résilience par offre.** Une source réelle émet du bruit : une offre dont l'analyse
échoue (texte vide, sortie LLM non conforme, LLM indisponible) est consignée dans le
rapport et la passe **continue** — un élément malformé ne doit pas faire tomber tout un
lot. Les échecs sont rendus visibles (``CollectionReport.failures``), jamais avalés.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.html_extract import extract_offer_text
from app.llm_client import LLMClient, LLMError
from app.offer import compute_offer_id
from app.offer_analysis import OfferAnalysisError
from app.offer_intake_service import intake_offer_enriched
from app.offer_source import RawOffer, SourceOffres
from app.offer_store import OfferRepository
from app.url_fetch import HtmlDocument, fetch_html


@dataclass(frozen=True)
class CollectionFailure:
    """Offre brute dont l'intake a échoué, avec le message d'erreur associé."""

    raw: RawOffer
    error: str


@dataclass(frozen=True)
class CollectionProgress:
    """Instantané des compteurs d'une passe en cours (OPP-170).

    Émis après le traitement de **chaque** offre via le callback ``on_progress`` de
    ``collect_offers`` : il permet à un job de fond de publier son avancement pendant que
    la passe tourne (sondage côté front). Mêmes compteurs que ``CollectionReport``, mais
    photographiés en cours de route — ``failures`` est ici le **cardinal** courant.
    """

    collected: int
    stored: int
    duplicates: int
    failures: int
    enriched: int
    enriched_recovered: int


@dataclass(frozen=True)
class CollectionReport:
    """Bilan d'une passe de collecte.

    ``collected`` = offres émises par la source ; ``stored`` = offres neuves persistées ;
    ``duplicates`` = offres écartées car déjà connues ; ``failures`` = offres dont
    l'intake a échoué (analyse/LLM). Invariant : ``collected == stored + duplicates +
    len(failures)``.

    ``source_error`` est renseigné si la source elle-même a échoué (``fetch`` ou
    itération : réseau, parsing du flux…) : la passe s'arrête alors, mais les offres
    déjà traitées restent persistées et comptées, et l'erreur est rendue visible plutôt
    qu'avalée.

    ``enriched`` / ``enriched_recovered`` (OPP-169) rendent l'enrichissement visible :
    ``enriched`` = offres neuves dont l'analyse du texte de la source n'a produit aucune
    compétence et qui ont donc déclenché une récupération de la page complète ;
    ``enriched_recovered`` = parmi elles, combien ont **effectivement** gagné des compétences
    après ré-analyse. Ce sont des sous-comptes de ``stored`` (``enriched_recovered`` ≤
    ``enriched`` ≤ ``stored``).
    """

    collected: int
    stored: int
    duplicates: int
    failures: tuple[CollectionFailure, ...]
    source_error: str | None = None
    enriched: int = 0
    enriched_recovered: int = 0


def collect_offers(
    source: SourceOffres,
    *,
    client: LLMClient,
    store: OfferRepository,
    fetch: Callable[[str], HtmlDocument] = fetch_html,
    extract: Callable[[str], str] = extract_offer_text,
    on_progress: Callable[[CollectionProgress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> CollectionReport:
    """Collecte, dédoublonne, analyse et persiste les offres d'une ``source``.

    Retourne un ``CollectionReport``. Les échecs d'intake (``ValueError``,
    ``OfferAnalysisError``, ``LLMError``) sont capturés par offre et consignés dans
    ``failures`` sans interrompre la passe. Un échec de la **source** (``fetch`` ou
    itération) arrête la passe mais est consigné dans ``source_error`` : les offres déjà
    traitées restent persistées et comptées.

    **Enrichissement en secours (OPP-169).** Chaque offre neuve passe par
    ``intake_offer_enriched`` : si l'analyse du texte de la source ne produit aucune
    compétence et qu'une URL est disponible, la page complète est récupérée et ré-analysée
    (cf. ``offer_intake_service``). ``fetch``/``extract`` sont injectables pour les tests.

    **Progression (OPP-170).** Si ``on_progress`` est fourni, il est appelé avec un
    ``CollectionProgress`` après le traitement de chaque offre (neuve, doublon ou échec) —
    de quoi publier l'avancement d'un job de fond pendant la passe. Les exceptions levées
    par le callback ne sont pas interceptées (c'est au job de les contenir).

    **Annulation coopérative (OPP-209).** Si ``should_cancel`` est fourni, il est consulté
    **au début de chaque tour**, avant de consommer l'offre suivante : s'il rend vrai, la
    passe s'arrête proprement et rend le bilan **partiel**. L'offre en cours de traitement
    (l'appel LLM, étape longue) n'est jamais interrompue en plein vol, et tout ce qui est
    déjà persisté le reste — c'est un arrêt **entre** offres, pas un `kill`.
    """
    collected = 0
    stored = 0
    duplicates = 0
    enriched = 0
    enriched_recovered = 0
    failures: list[CollectionFailure] = []
    seen: set[str] = set()
    source_error: str | None = None

    def _emit() -> None:
        if on_progress is not None:
            on_progress(
                CollectionProgress(
                    collected=collected,
                    stored=stored,
                    duplicates=duplicates,
                    failures=len(failures),
                    enriched=enriched,
                    enriched_recovered=enriched_recovered,
                )
            )

    # Itération manuelle : on isole les erreurs de la source (``fetch``/``next``) des
    # échecs d'intake par offre. Une source réelle (réseau, flux) peut échouer au départ
    # ou en cours de route — on la rend visible sans faire tomber toute la passe, et sans
    # masquer un bug du corps de boucle (qui, lui, reste géré par le try ciblé interne).
    try:
        iterator = iter(source.fetch())
    except Exception as exc:  # noqa: BLE001 — remonté dans le rapport, jamais avalé
        return CollectionReport(0, 0, 0, (), source_error=f"{type(exc).__name__}: {exc}")

    while True:
        # Arrêt coopératif (OPP-209) : vérifié entre deux offres, jamais pendant un intake LLM
        # en cours. Le bilan déjà accumulé est rendu tel quel (offres persistées conservées).
        if should_cancel is not None and should_cancel():
            break
        try:
            raw = next(iterator)
        except StopIteration:
            break
        except Exception as exc:  # noqa: BLE001 — échec de la source, consigné et arrêt
            source_error = f"{type(exc).__name__}: {exc}"
            break

        collected += 1
        offer_id = compute_offer_id(raw.source, raw.url, raw.raw_text)
        # Déjà vue dans cette passe, ou déjà persistée : on évite l'appel LLM.
        if offer_id in seen or store.get(offer_id) is not None:
            duplicates += 1
            _emit()
            continue
        seen.add(offer_id)
        try:
            result = intake_offer_enriched(
                raw.raw_text,
                source=raw.source,
                url=raw.url,
                client=client,
                store=store,
                fetch=fetch,
                extract=extract,
            )
        except (ValueError, OfferAnalysisError, LLMError) as exc:
            failures.append(CollectionFailure(raw=raw, error=str(exc)))
            _emit()
            continue
        stored += 1
        if result.enrichment_attempted:
            enriched += 1
        if result.enrichment_recovered:
            enriched_recovered += 1
        _emit()

    return CollectionReport(
        collected=collected,
        stored=stored,
        duplicates=duplicates,
        failures=tuple(failures),
        source_error=source_error,
        enriched=enriched,
        enriched_recovered=enriched_recovered,
    )
