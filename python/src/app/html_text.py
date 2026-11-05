"""Conversion d'un fragment HTML en texte lisible, avec la bibliothèque standard (OPP-226).

Les API d'ATS renvoient des descriptions d'offres en **fragments HTML** propres (paragraphes,
listes, titres), pas des pages complètes : pas besoin de l'extraction « readability » de
``html_extract`` (BeautifulSoup, extra ``scrape``). ``html.parser`` suffit, ce qui garde le
connecteur ATS sans dépendance.

Chaque bloc (``p``, ``li``, ``h1``…, ``br``) passe à la ligne ; les ``li`` sont préfixés d'un
tiret ; le contenu de ``script``/``style`` est ignoré ; les entités sont décodées.
"""

from __future__ import annotations

from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "tr", "table", "section", "article", "blockquote", "hr",
}
_SKIPPED_TAGS = {"script", "style", "template", "noscript"}


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 - signature imposée
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)


def html_to_text(fragment: str) -> str:
    """Texte lisible d'un fragment HTML : une ligne par bloc, blancs normalisés, ``""`` si vide."""
    if not isinstance(fragment, str) or not fragment.strip():
        return ""
    collector = _TextCollector()
    collector.feed(fragment)
    collector.close()
    lines = (" ".join(line.split()) for line in "".join(collector.parts).splitlines())
    # Un tiret de liste resté seul (``<li>`` vide) n'apporte rien.
    return "\n".join(line for line in lines if line and line != "-")
