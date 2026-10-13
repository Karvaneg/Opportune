"""Source d'offres RSS/Atom — implémentation du port ``SourceOffres`` (V1, OPP-122).

Troisième type de source de la vision (après les API France Travail/Adzuna) : les **flux RSS**
d'alertes emploi. Adaptateur mince entre le parseur (``rss_feed``) et le pipeline de collecte
(``offer_collection``) : il émet des ``RawOffer`` et ne porte aucune logique d'analyse ni de
persistance — le socle OPP-119 dédoublonne *avant* le LLM et normalise en aval.

Trois responsabilités, toutes déléguées à des briques existantes :

- **Fetch SSRF-safe.** Le XML de chaque flux est récupéré via ``url_fetch.fetch_html`` (schéma
  http(s) validé, cibles internes refusées, redirections revalidées) — injectable pour des
  tests hermétiques.
- **Parsing.** ``rss_feed.parse_feed`` transforme le XML en ``FeedItem`` (RSS/RDF/Atom).
- **Nettoyage.** Le contenu d'un article est souvent du HTML : ``html_extract.extract_offer_text``
  le dégrossit en texte lisible avant de composer le ``raw_text`` (``source_support``).

Plusieurs flux sont parcourus en séquence. L'échec d'un flux (réseau, XML malformé) se propage
au pipeline, consigné en ``source_error`` — fidèle au modèle des autres connecteurs : une source
qui casse arrête la passe en préservant les offres déjà émises, sans faire tomber le process.
"""

from __future__ import annotations

from typing import Callable, Iterable, Iterator

from app.html_extract import extract_offer_text
from app.rss_feed import FeedItem, parse_feed
from app.source_support import assemble_raw_text
from app.offer_source import RawOffer
from app.url_fetch import fetch_html

# Provenance estampillée sur chaque offre (champ ``RawOffer.source``).
SOURCE_NAME = "rss"

# Fetch d'un flux : URL -> corps XML. Injectable (tests) ; défaut = fetch HTTP SSRF-safe.
FeedFetch = Callable[[str], str]


def _default_fetch(url: str) -> str:
    """Fetch réel d'un flux : délègue à ``fetch_html`` (SSRF-safe) et rend le corps brut."""
    return fetch_html(url).html


def _to_raw_offer(item: FeedItem) -> RawOffer:
    """Convertit un ``FeedItem`` en ``RawOffer`` : HTML du contenu nettoyé, titre en en-tête.

    ``assemble_raw_text`` place le titre en en-tête et le contenu nettoyé en corps ; les champs
    structurés (entreprise, lieu, contrat) ne sont pas fiables en RSS, l'analyse LLM les extraira
    du texte en aval. Le lien de l'article sert de clé de dédoublonnage (canonicalisée côté socle).
    """
    description = extract_offer_text(item.summary) if item.summary else ""
    raw_text = assemble_raw_text(
        title=item.title, company="", location="", contract="", description=description
    )
    return RawOffer(source=SOURCE_NAME, raw_text=raw_text, url=item.link)


class RssSource:
    """Source ``SourceOffres`` qui parcourt un ou plusieurs flux RSS/Atom et émet des ``RawOffer``.

    ``feed_urls`` est la liste des flux à collecter (ordre préservé). ``fetch`` est injectable
    (défaut : fetch HTTP SSRF-safe). ``max_offers`` plafonne le total émis sur l'ensemble des flux.
    """

    def __init__(
        self,
        feed_urls: Iterable[str],
        *,
        fetch: FeedFetch = _default_fetch,
        max_offers: int = 500,
    ) -> None:
        self._feed_urls = [url for url in feed_urls if url and url.strip()]
        self._fetch = fetch
        self._max_offers = max(1, max_offers)

    def fetch(self) -> Iterator[RawOffer]:
        """Itère les offres de chaque flux, jusqu'au plafond ``max_offers``.

        Générateur paresseux : chaque flux est récupéré puis parsé à la demande. Une erreur de
        fetch (``UrlFetchError``) ou de parsing (``RssParseError``) se propage — captée par le
        pipeline en ``source_error``. Les flux déjà consommés restent acquis.
        """
        emitted = 0
        for feed_url in self._feed_urls:
            if emitted >= self._max_offers:
                break
            for item in parse_feed(self._fetch(feed_url)):
                if emitted >= self._max_offers:
                    break
                yield _to_raw_offer(item)
                emitted += 1


def build_rss_source(
    feed_urls: Iterable[str],
    *,
    max_offers: int = 500,
) -> RssSource:
    """Assemble une ``RssSource`` sur ses flux avec le fetch HTTP réel (câblage prod)."""
    return RssSource(feed_urls, max_offers=max_offers)
