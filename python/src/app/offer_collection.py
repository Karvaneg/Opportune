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

from app.llm_client import LLMClient, LLMError
from app.offer import compute_offer_id
from app.offer_analysis import OfferAnalysisError
from app.offer_intake_service import intake_offer
from app.offer_source import RawOffer, SourceOffres
from app.offer_store import OfferRepository


@dataclass(frozen=True)
class CollectionFailure:
    """Offre brute dont l'intake a échoué, avec le message d'erreur associé."""

    raw: RawOffer
    error: str


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
    """

    collected: int
    stored: int
    duplicates: int
    failures: tuple[CollectionFailure, ...]
    source_error: str | None = None


def collect_offers(
    source: SourceOffres,
    *,
    client: LLMClient,
    store: OfferRepository,
) -> CollectionReport:
    """Collecte, dédoublonne, analyse et persiste les offres d'une ``source``.

    Retourne un ``CollectionReport``. Les échecs d'intake (``ValueError``,
    ``OfferAnalysisError``, ``LLMError``) sont capturés par offre et consignés dans
    ``failures`` sans interrompre la passe. Un échec de la **source** (``fetch`` ou
    itération) arrête la passe mais est consigné dans ``source_error`` : les offres déjà
    traitées restent persistées et comptées.
    """
    collected = 0
    stored = 0
    duplicates = 0
    failures: list[CollectionFailure] = []
    seen: set[str] = set()
    source_error: str | None = None

    # Itération manuelle : on isole les erreurs de la source (``fetch``/``next``) des
    # échecs d'intake par offre. Une source réelle (réseau, flux) peut échouer au départ
    # ou en cours de route — on la rend visible sans faire tomber toute la passe, et sans
    # masquer un bug du corps de boucle (qui, lui, reste géré par le try ciblé interne).
    try:
        iterator = iter(source.fetch())
    except Exception as exc:  # noqa: BLE001 — remonté dans le rapport, jamais avalé
        return CollectionReport(0, 0, 0, (), source_error=f"{type(exc).__name__}: {exc}")

    while True:
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
            continue
        seen.add(offer_id)
        try:
            intake_offer(
                raw.raw_text,
                source=raw.source,
                url=raw.url,
                client=client,
                store=store,
            )
        except (ValueError, OfferAnalysisError, LLMError) as exc:
            failures.append(CollectionFailure(raw=raw, error=str(exc)))
            continue
        stored += 1

    return CollectionReport(
        collected=collected,
        stored=stored,
        duplicates=duplicates,
        failures=tuple(failures),
        source_error=source_error,
    )
