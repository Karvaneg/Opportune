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
from app.candidate_offer_store import CandidateOfferRepository
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

    ``cancelled`` (OPP-209) vaut ``True`` quand la passe a été **effectivement** tronquée par
    ``should_cancel`` (arrêt entre deux offres), par opposition à une passe menée à terme. Il
    décrit ce qui s'est réellement produit — à ne pas confondre avec la *demande* d'arrêt : une
    annulation qui arrive une fois la dernière offre déjà traitée laisse ``cancelled`` à
    ``False`` (rien n'a été tronqué). Reste interne au back (non sérialisé vers le front).
    """

    collected: int
    stored: int
    duplicates: int
    failures: tuple[CollectionFailure, ...]
    source_error: str | None = None
    enriched: int = 0
    enriched_recovered: int = 0
    cancelled: bool = False
    # Renseignés par l'appelant pour la source « entreprises ciblées » (OPP-226), le pipeline ne
    # les connaît pas : ``excluded`` = offres non émises car hors France (ni doublons ni échecs,
    # donc hors de l'invariant ci-dessus) ; ``off_target`` = offres en France non émises car leur
    # intitulé ne contient pas le poste saisi (même statut) ; ``warnings`` = entreprises en échec.
    excluded: int = 0
    off_target: int = 0
    warnings: tuple[str, ...] = ()


# Marge accordée à une source quand la passe est plafonnée en offres **neuves** (``max_new``) :
# la source peut émettre jusqu'à ``max_new × SOURCE_CAP_FACTOR`` offres, pour que les doublons
# d'une passe précédente ne consomment pas tout le plafond, sans laisser une source paginée
# (quota Adzuna) lire indéfiniment quand presque tout est déjà connu.
SOURCE_CAP_FACTOR = 5


def source_cap(max_new: int) -> int:
    """Plafond d'offres à émettre par la source pour viser ``max_new`` offres neuves."""
    return max(1, max_new) * SOURCE_CAP_FACTOR


def collect_offers(
    source: SourceOffres,
    *,
    client: LLMClient,
    store: OfferRepository,
    fetch: Callable[[str], HtmlDocument] = fetch_html,
    extract: Callable[[str], str] = extract_offer_text,
    on_progress: Callable[[CollectionProgress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    max_new: int | None = None,
    candidate_id: str | None = None,
    memberships: CandidateOfferRepository | None = None,
) -> CollectionReport:
    """Collecte, dédoublonne, analyse et persiste les offres d'une ``source``.

    **Recherche cible (OPP-186).** Avec ``candidate_id`` et ``memberships``, chaque offre
    persistée est rattachée à cette recherche. Une offre déjà en base mais pas encore liée à la
    recherche est liée **sans appel au LLM** et comptée dans ``stored`` : elle est nouvelle pour
    cette recherche. ``duplicates`` ne compte alors que les offres déjà liées à la recherche (ou
    vues deux fois dans la passe). Sans eux, comportement d'origine : toute offre déjà en base
    est un doublon.

    **Plafond en offres neuves.** Si ``max_new`` est fourni, la passe s'arrête dès que
    ``max_new`` offres **neuves** ont été traitées (persistées ou en échec). Les doublons ne
    comptent pas : une passe relancée ne bute plus sur les mêmes premières offres déjà connues.
    La source, elle, est plafonnée plus large par l'appelant (``source_cap``) ; comme on cesse
    de la consommer, une source paginée ne lit pas de page de plus que nécessaire.

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
    if (candidate_id is None) != (memberships is None):
        raise ValueError("candidate_id et memberships vont ensemble")
    collected = 0
    stored = 0
    duplicates = 0
    enriched = 0
    enriched_recovered = 0
    failures: list[CollectionFailure] = []
    seen: set[str] = set()
    source_error: str | None = None
    cancelled = False

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
        if max_new is not None and stored + len(failures) >= max_new:
            break
        # Arrêt coopératif (OPP-209) : vérifié entre deux offres, jamais pendant un intake LLM
        # en cours. Le bilan déjà accumulé est rendu tel quel (offres persistées conservées).
        # ``cancelled`` ne passe à vrai que si l'on rompt **ici** : une annulation posée après
        # la dernière offre ne tronque rien et laisse la passe se terminer normalement.
        if should_cancel is not None and should_cancel():
            cancelled = True
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
        if offer_id in seen:
            duplicates += 1
            _emit()
            continue
        seen.add(offer_id)
        if store.get(offer_id) is not None:
            if memberships is not None and not memberships.is_linked(candidate_id, offer_id):
                # Déjà en base (collectée par une autre recherche) : on la lie, sans LLM.
                memberships.link(candidate_id, offer_id)
                stored += 1
            else:
                duplicates += 1
            _emit()
            continue
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
        if memberships is not None:
            memberships.link(candidate_id, result.offer.id)
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
        cancelled=cancelled,
    )
