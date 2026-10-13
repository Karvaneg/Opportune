"""Source d'offres France Travail — implémentation du port ``SourceOffres`` (V1, OPP-120).

Adaptateur mince entre le client bas niveau (``france_travail_client``) et le pipeline de
collecte (``offer_collection``) : il **implémente le port** ``SourceOffres`` en émettant des
``RawOffer`` CDI, et ne porte aucune logique d'analyse ni de persistance — c'est tout
l'intérêt du socle OPP-119, qui dédoublonne *avant* le LLM et normalise en aval.

Deux traductions, et deux seulement :

- **Pagination → itération.** ``fetch`` obtient un jeton, puis enchaîne les pages (``range``)
  jusqu'à épuisement du total annoncé ou de la fenêtre dure de l'API (~1150). Générateur :
  une panne du client en cours de route (quota, réseau) remonte au pipeline, qui la consigne
  dans ``source_error`` sans faire tomber la passe ni perdre les offres déjà émises.
- **Offre API → ``RawOffer``.** Les champs structurés (intitulé, entreprise, lieu, contrat,
  description) sont recomposés en un ``raw_text`` lisible que l'intake LLM ré-analyse — on ne
  court-circuite pas la chaîne existante. L'``url`` (lien d'origine, sinon détail candidat)
  sert de clé de dédoublonnage stable côté socle.
"""

from __future__ import annotations

from typing import Iterator, Mapping

from app.france_travail_client import (
    PAGE_SIZE_MAX,
    RANGE_END_MAX,
    RANGE_START_MAX,
    WINDOW_MAX,
    FranceTravailClient,
    credentials_from_env,
)
from app.offer_source import RawOffer
from app.source_support import assemble_raw_text, clamp

# Provenance estampillée sur chaque offre (champ ``RawOffer.source``).
SOURCE_NAME = "france-travail"
# URL de détail candidat, repli quand l'offre ne porte pas de lien d'origine.
_DETAIL_URL = "https://candidat.francetravail.fr/offres/recherche/detail/"


def _offer_url(offer: dict) -> str:
    """URL de l'offre : lien d'origine si fourni, sinon détail candidat construit sur l'id.

    L'URL est la clé de dédoublonnage en aval (``compute_offer_id`` la canonicalise) : on
    privilégie donc un lien stable. ``origineOffre.urlOrigine`` est renseigné pour les offres
    partenaires ; à défaut on reconstruit l'URL de détail depuis l'identifiant. Sans id ni
    lien, chaîne vide (le socle retombe alors sur le texte brut comme clé).
    """
    origin = offer.get("origineOffre") or {}
    url = (origin.get("urlOrigine") or "").strip()
    if url:
        return url
    offer_id = (offer.get("id") or "").strip()
    return f"{_DETAIL_URL}{offer_id}" if offer_id else ""


def _raw_text(offer: dict) -> str:
    """Recompose un texte d'offre lisible à partir des champs structurés de l'API.

    Extrait les champs propres à France Travail (intitulé, entreprise, lieu, contrat,
    description) puis délègue l'assemblage à ``assemble_raw_text`` (socle partagé).
    """
    return assemble_raw_text(
        title=(offer.get("intitule") or "").strip(),
        company=((offer.get("entreprise") or {}).get("nom") or "").strip(),
        location=((offer.get("lieuTravail") or {}).get("libelle") or "").strip(),
        contract=(offer.get("typeContratLibelle") or offer.get("typeContrat") or "").strip(),
        description=(offer.get("description") or "").strip(),
    )


def _to_raw_offer(offer: dict) -> RawOffer:
    """Convertit une offre JSON de l'API en ``RawOffer`` (texte recomposé + url de dédup)."""
    return RawOffer(source=SOURCE_NAME, raw_text=_raw_text(offer), url=_offer_url(offer))


class FranceTravailSource:
    """Source ``SourceOffres`` qui pagine l'API France Travail et émet des ``RawOffer`` CDI.

    ``page_size`` et ``max_offers`` sont bornés aux limites de l'API (≤ 150 par page, fenêtre
    ~1150) : une valeur hors bornes est ramenée sans erreur. ``filters`` (facultatif) est passé
    tel quel à la recherche (mots-clés, code ROME, commune…) pour cibler la collecte.
    """

    def __init__(
        self,
        client: FranceTravailClient,
        *,
        page_size: int = PAGE_SIZE_MAX,
        max_offers: int = WINDOW_MAX,
        filters: "Mapping[str, str] | None" = None,
    ) -> None:
        self._client = client
        self._page_size = clamp(page_size, 1, PAGE_SIZE_MAX)
        self._max_offers = clamp(max_offers, 1, WINDOW_MAX)
        self._filters = dict(filters) if filters else None

    def fetch(self) -> Iterator[RawOffer]:
        """Itère les offres CDI de l'API, page par page, jusqu'au total ou à la fenêtre max.

        Générateur paresseux : le jeton est obtenu au premier ``next`` et les pages sont
        récupérées à la demande. S'arrête dès qu'une page est vide, que le total annoncé est
        atteint, ou que la fenêtre dure est franchie. Toute erreur du client
        (``FranceTravail*``) se propage telle quelle — captée par le pipeline en ``source_error``.
        """
        token = self._client.fetch_token()
        start = 0
        # ``start <= RANGE_START_MAX`` : au-delà, l'API refuse le range (400). Avec des pages
        # pleines on s'arrête donc un peu avant ``max_offers`` — acceptable : une requête
        # ciblée (filtres) ramène très en deçà de la fenêtre dure.
        while start < self._max_offers and start <= RANGE_START_MAX:
            end = min(start + self._page_size - 1, self._max_offers - 1, RANGE_END_MAX)
            page = self._client.search(
                token=token, start=start, end=end, extra_params=self._filters
            )
            if not page.offers:
                break
            for offer in page.offers:
                yield _to_raw_offer(offer)
            start += len(page.offers)
            # Total atteint, ou page partielle (dernière page) : rien de plus à récupérer.
            if start >= page.total or len(page.offers) < self._page_size:
                break


def build_france_travail_source(
    env: Mapping[str, str],
    *,
    filters: "Mapping[str, str] | None" = None,
    max_offers: int = WINDOW_MAX,
) -> FranceTravailSource:
    """Assemble une ``FranceTravailSource`` à partir de l'environnement (câblage prod).

    Unique endroit qui touche à la configuration réelle : lit les identifiants OAuth2 de
    l'environnement (``credentials_from_env``) et construit le client avec son transport
    ``urllib`` par défaut. Lève ``FranceTravailAuthError`` si les identifiants manquent.
    """
    client = FranceTravailClient(credentials_from_env(env))
    return FranceTravailSource(client, filters=filters, max_offers=max_offers)
