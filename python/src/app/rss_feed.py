"""Parsing d'un flux d'offres RSS/Atom (V1, OPP-122).

Cœur **pur** du connecteur RSS : transforme le XML brut d'un flux en une liste de ``FeedItem``
structurés, sans aucun appel réseau — donc entièrement testable. Le fetch (SSRF-safe) et le
nettoyage HTML du contenu sont l'affaire de ``rss_source`` ; ici on ne fait que lire le XML.

**Un seul parseur pour les trois familles.** RSS 2.0 (``<item>``), RSS 1.0/RDF (``<item>`` aussi,
mais sous un autre namespace) et Atom (``<entry>``) décrivent la même chose avec des balises et
des namespaces différents. Plutôt que de router par dialecte, on raisonne sur le **nom local**
des balises (sans namespace) : un article est un élément ``item`` ou ``entry`` ; son lien est
le texte d'un ``link`` (RSS) **ou** l'attribut ``href`` d'un ``link`` (Atom) ; son contenu est,
par ordre de richesse, ``content:encoded`` > ``content`` > ``summary`` > ``description``.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree


class RssParseError(Exception):
    """Le flux n'a pu être parsé : XML malformé ou racine non reconnue comme un flux."""


@dataclass(frozen=True)
class FeedItem:
    """Un article de flux, avant nettoyage : titre, lien, et contenu brut (souvent du HTML)."""

    title: str
    link: str
    summary: str


# Noms locaux (sans namespace) des balises d'un article, par famille de flux.
_ITEM_TAGS = ("item", "entry")
# Balises de contenu, de la plus riche à la plus pauvre : on garde la première renseignée.
_SUMMARY_TAGS = ("encoded", "content", "summary", "description")


def _local(tag: str) -> str:
    """Nom local d'une balise, namespace retiré : ``{http://…}entry`` → ``entry``."""
    return tag.rsplit("}", 1)[-1]


def _child_text(item: ElementTree.Element, local_name: str) -> str:
    """Texte du premier enfant direct portant ce nom local (chaîne vide sinon)."""
    for child in item:
        if _local(child.tag) == local_name and child.text:
            return child.text.strip()
    return ""


def _extract_link(item: ElementTree.Element) -> str:
    """Lien de l'article : texte d'un ``<link>`` (RSS) ou attribut ``href`` (Atom).

    Atom expose plusieurs ``<link>`` (``alternate``, ``self``…) : on privilégie ``alternate``
    (ou l'absence de ``rel``, qui vaut ``alternate``), à défaut le premier ``href`` rencontré.
    """
    fallback_href = ""
    for child in item:
        if _local(child.tag) != "link":
            continue
        if child.text and child.text.strip():  # forme RSS : le lien est le texte
            return child.text.strip()
        href = child.get("href", "").strip()  # forme Atom : le lien est dans href
        if not href:
            continue
        if child.get("rel", "alternate") == "alternate":
            return href
        fallback_href = fallback_href or href
    return fallback_href


def _extract_summary(item: ElementTree.Element) -> str:
    """Contenu de l'article : la première balise renseignée par ordre de richesse."""
    for tag in _SUMMARY_TAGS:
        text = _child_text(item, tag)
        if text:
            return text
    return ""


def parse_feed(xml: str) -> list[FeedItem]:
    """Parse le XML d'un flux RSS/Atom en liste de ``FeedItem`` (ordre du flux préservé).

    Lève ``RssParseError`` si le XML est malformé. Un flux syntaxiquement valide mais sans
    aucun article renvoie une liste vide (pas une erreur : un flux peut être vide). Les articles
    sans titre **ni** contenu sont ignorés (bruit structurel), mais un titre seul suffit.
    """
    if not isinstance(xml, str) or xml.strip() == "":
        raise RssParseError("flux vide")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise RssParseError(f"XML malformé : {exc}") from exc

    items: list[FeedItem] = []
    for element in root.iter():
        if _local(element.tag) not in _ITEM_TAGS:
            continue
        title = _child_text(element, "title")
        summary = _extract_summary(element)
        if not title and not summary:
            continue
        items.append(FeedItem(title=title, link=_extract_link(element), summary=summary))
    return items
