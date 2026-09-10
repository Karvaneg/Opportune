"""Extraction de texte d'un CV PDF (V2, OPP-137).

Adaptateur d'entrée du runner d'intake de profil : lit un PDF et en extrait le texte
brut, que ``analyze_cv`` (OPP-136) transforme en profil. La dépendance **pypdf** est
optionnelle (extra ``[pdf]``) et importée **paresseusement** — le cœur métier reste sans
dépendance, comme la gateway Discord confine ``discord.py`` (OPP-125).

Le lecteur de pages est **injectable** (``read_pages``) : la logique propre à ce module
(jointure des pages, rejet d'un texte vide) est testable sans pypdf ni fichier réel.
"""

from __future__ import annotations

from typing import Callable

# Un lecteur de pages prend un chemin et retourne le texte de chaque page.
PageReader = Callable[[str], list[str]]


class PdfExtractionError(Exception):
    """Extraction impossible : PDF illisible/vide, scanné (pas d'OCR), ou pypdf absent."""


def _pypdf_page_reader(path: str) -> list[str]:
    """Lecteur par défaut : ouvre le PDF via pypdf et retourne le texte de chaque page.

    Import paresseux : un ``PdfExtractionError`` explicite (pointant vers l'extra) est levé
    si pypdf n'est pas installé, plutôt qu'un ``ImportError`` brut au chargement du module.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PdfExtractionError(
            'pypdf n\'est pas installé : `pip install -e ".[pdf]"` pour lire un CV PDF.'
        ) from exc
    reader = PdfReader(path)
    return [page.extract_text() or "" for page in reader.pages]


def extract_text_from_pdf(path: str, *, read_pages: PageReader | None = None) -> str:
    """Extrait le texte concaténé d'un PDF ; lève ``PdfExtractionError`` si rien d'exploitable.

    ``read_pages`` (injectable) retourne la liste des textes de page ; par défaut pypdf. Un
    PDF vide ou scanné (pypdf n'en tire aucun texte) est rejeté explicitement plutôt que de
    produire un profil vide en aval. Lève ``ValueError`` si le chemin est vide.
    """
    if not isinstance(path, str) or path.strip() == "":
        raise ValueError("Le chemin du PDF est requis")
    pages = (read_pages or _pypdf_page_reader)(path)
    # Chaque page est strippée avant jointure : une page vide est écartée, et les pages
    # retenues sont séparées par un seul saut de ligne (pas de blancs de mise en page).
    text = "\n".join(page.strip() for page in pages if page and page.strip())
    if not text:
        raise PdfExtractionError(
            f"Aucun texte extrait de {path!r} (PDF vide ou scanné sans OCR ?)"
        )
    return text
