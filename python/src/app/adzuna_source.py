"""Source d'offres Adzuna — implémentation du port ``SourceOffres`` (V1, OPP-120).

Connecteur **actif** d'Opportune : adaptateur mince entre le client Adzuna
(``adzuna_client``) et le pipeline de collecte (``offer_collection``). Il émet des ``RawOffer``
en ciblant par défaut les contrats **permanents** (``permanent=1`` ≈ CDI) et ne porte aucune
logique d'analyse ni de persistance — le socle OPP-119 dédoublonne *avant* le LLM et normalise
en aval.

Deux traductions :

- **Pagination → itération.** ``fetch`` enchaîne les pages (numéro 1-indexé) jusqu'au total
  annoncé (``count``) ou au plafond ``max_offers``. Générateur : une panne du client (quota,
  réseau) remonte au pipeline, consignée en ``source_error`` sans perdre les offres déjà émises.
- **Offre Adzuna → ``RawOffer``.** Les champs (titre, entreprise, lieu, contrat, extrait de
  description) sont recomposés en un ``raw_text`` lisible que l'intake LLM ré-analyse. Le
  ``redirect_url`` sert de clé de dédoublonnage stable côté socle.
"""

from __future__ import annotations

from typing import Iterator, Mapping

from app.adzuna_client import (
    DEFAULT_COUNTRY,
    RESULTS_PER_PAGE_MAX,
    AdzunaClient,
    credentials_from_env,
)
from app.offer_source import RawOffer
from app.source_support import assemble_raw_text, clamp

# Provenance estampillée sur chaque offre (champ ``RawOffer.source``).
SOURCE_NAME = "adzuna"
# Plafond d'offres par défaut d'une passe : modéré pour ménager le quota gratuit
# (2 500 appels/mois). Ajustable par ``max_offers`` / l'option ``--max`` du runner.
DEFAULT_MAX_OFFERS = 200


def _raw_text(offer: dict) -> str:
    """Recompose un texte d'offre lisible à partir des champs structurés d'Adzuna.

    Extrait les champs propres à Adzuna (titre, entreprise, lieu, contrat, extrait de
    description) puis délègue l'assemblage à ``assemble_raw_text`` (socle partagé).
    """
    contract = " ".join(
        part for part in (offer.get("contract_type"), offer.get("contract_time")) if part
    ).strip()
    return assemble_raw_text(
        title=(offer.get("title") or "").strip(),
        company=((offer.get("company") or {}).get("display_name") or "").strip(),
        location=((offer.get("location") or {}).get("display_name") or "").strip(),
        contract=contract,
        description=(offer.get("description") or "").strip(),
    )


def _to_raw_offer(offer: dict) -> RawOffer:
    """Convertit une offre JSON Adzuna en ``RawOffer`` (texte recomposé + url de dédup)."""
    return RawOffer(
        source=SOURCE_NAME,
        raw_text=_raw_text(offer),
        url=(offer.get("redirect_url") or "").strip(),
    )


class AdzunaSource:
    """Source ``SourceOffres`` qui pagine l'API Adzuna et émet des ``RawOffer``.

    Cible par défaut les contrats **permanents** (``permanent=1`` ≈ CDI) ; ``permanent=False``
    lève ce filtre. ``filters`` (``what``, ``where``, ``category``…) est passé tel quel à la
    recherche. ``page_size`` est borné au maximum de l'API (50) et ``max_offers`` au plafond de
    passe.
    """

    def __init__(
        self,
        client: AdzunaClient,
        *,
        page_size: int = RESULTS_PER_PAGE_MAX,
        max_offers: int = DEFAULT_MAX_OFFERS,
        filters: "Mapping[str, str] | None" = None,
        permanent: bool = True,
    ) -> None:
        self._client = client
        self._page_size = clamp(page_size, 1, RESULTS_PER_PAGE_MAX)
        self._max_offers = max(1, max_offers)
        merged = dict(filters) if filters else {}
        if permanent:
            merged.setdefault("permanent", "1")
        self._filters = merged or None

    def fetch(self) -> Iterator[RawOffer]:
        """Itère les offres de l'API, page par page, jusqu'au total ou au plafond ``max_offers``.

        Générateur paresseux : les pages sont récupérées à la demande. S'arrête dès qu'une page
        est vide, que le total annoncé est atteint, ou que le plafond est franchi. Toute erreur
        du client (``Adzuna*``) se propage telle quelle — captée par le pipeline en ``source_error``.
        """
        page = 1
        collected = 0
        while collected < self._max_offers:
            results_per_page = min(self._page_size, self._max_offers - collected)
            search_page = self._client.search(
                page=page, results_per_page=results_per_page, extra_params=self._filters
            )
            if not search_page.offers:
                break
            for offer in search_page.offers:
                if collected >= self._max_offers:
                    break
                yield _to_raw_offer(offer)
                collected += 1
            # Total atteint, ou page partielle (dernière page) : rien de plus à récupérer.
            if collected >= search_page.total or len(search_page.offers) < results_per_page:
                break
            page += 1


def build_adzuna_source(
    env: Mapping[str, str],
    *,
    filters: "Mapping[str, str] | None" = None,
    max_offers: int = DEFAULT_MAX_OFFERS,
    country: str = DEFAULT_COUNTRY,
    permanent: bool = True,
) -> AdzunaSource:
    """Assemble une ``AdzunaSource`` à partir de l'environnement (câblage prod).

    Unique endroit qui touche à la configuration réelle : lit les identifiants de
    l'environnement (``credentials_from_env``) et construit le client avec son transport
    ``urllib`` par défaut. Lève ``AdzunaAuthError`` si les identifiants manquent.
    """
    client = AdzunaClient(credentials_from_env(env), country=country)
    return AdzunaSource(client, max_offers=max_offers, filters=filters, permanent=permanent)
