"""Modèle de lettre de motivation **persistée** (V2, OPP-147).

``Letter`` est la lettre telle qu'elle vit en base, clé = ``recommendation_id`` (une
lettre par recommandation). Elle se distingue de ``CoverLetter`` (``app.cover_letter``),
qui est le **résultat brut du Rédacteur** au moment de la génération : ``Letter`` ajoute
l'identité (la reco), la **provenance** (``ai`` générée / ``human`` éditée à la main) et
les horodatages. La provenance porte la règle produit d'OPP-147 : une lettre éditée à la
main n'est jamais écrasée en silence par une régénération (le choix revient à l'humain).

Ce module ne parle ni au LLM ni à SQLite : il fixe le contrat de données et **valide**
(corps non vide, provenance connue), fidèle à la philosophie de la stack.
"""

from __future__ import annotations

from dataclasses import dataclass

# Provenance d'une lettre : générée par le LLM, ou éditée/écrite par un humain.
SOURCE_AI = "ai"
SOURCE_HUMAN = "human"
SOURCES = frozenset({SOURCE_AI, SOURCE_HUMAN})


class LetterError(Exception):
    """Lettre invalide : corps vide ou provenance inconnue."""


@dataclass(frozen=True)
class Letter:
    """Lettre de motivation persistée, rattachée à une recommandation."""

    recommendation_id: str
    body: str
    source: str  # SOURCE_AI | SOURCE_HUMAN
    model: str = ""  # modèle LLM d'une lettre générée ; "" pour une édition humaine
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.body, str) or self.body.strip() == "":
            raise LetterError("corps de lettre vide : lettre inexploitable")
        if self.source not in SOURCES:
            raise LetterError(
                f"provenance inconnue : {self.source!r} (attendu : {', '.join(sorted(SOURCES))})"
            )
