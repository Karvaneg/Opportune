"""Type d'offre : emploi vs formation (V2, OPP-166).

Une **formation** (ex. une POE « Préparation Opérationnelle à l'Emploi ») n'est pas une
offre d'emploi : son but est d'**acquérir** des compétences, pas d'en exiger. La scorer
sur l'adéquation « compétences requises ↔ détenues » (cf. ``offer_score``) n'a aucun sens
et la fait chuter à 0 à tort. On distingue donc deux types (``emploi`` par défaut,
``formation``) pour **ne pas** scorer les formations comme des emplois.

La classification est une **heuristique déterministe** sur le titre et le texte brut :
- un marqueur de **titre** (« formation », « bootcamp », « cursus »…) suffit (le titre
  annonce la nature de l'offre) ;
- sinon, au moins deux **marqueurs structurels forts** (tournures propres à un programme
  de formation : « POE », « programme de formation », « éligible au financement »…), qui
  n'apparaissent quasiment jamais dans une offre d'emploi ordinaire. Le seuil à deux évite
  qu'un simple « formation continue proposée » d'une annonce d'emploi ne la bascule.

Déterministe, sans LLM ni I/O : exploitable tel quel pour re-typer la base existante
(``OfferStore``, pas de LLM à la migration) comme en filet de l'intake (``resolve_kind``).
"""

from __future__ import annotations

import re
import unicodedata

EMPLOI = "emploi"
FORMATION = "formation"
OFFER_KINDS = (EMPLOI, FORMATION)
DEFAULT_KIND = EMPLOI

# Marqueurs de **titre** : si le titre les contient, l'offre annonce elle-même une formation.
_TITLE_MARKERS = (
    "formation",
    "bootcamp",
    "cursus",
    "certifiante",
    "certifiant",
    "diplomante",
    "diplomant",
    "mooc",
)

# Marqueurs **structurels forts** : tournures d'un programme de formation, quasi absentes
# d'une annonce d'emploi. Le seuil (``_STRONG_THRESHOLD``) exige d'en trouver plusieurs pour
# conclure, afin qu'une mention isolée (« budget formation ») ne suffise pas.
_STRONG_MARKERS = (
    "preparation operationnelle",
    "poe",
    "cpf",
    "eligible au financement",
    "formation eligible",
    "programme de formation",
    "centre de formation",
    "organisme de formation",
    "module de formation",
    "heures de formation",
    "duree de la formation",
    "prerequis de la formation",
    "bootcamp",
    "certifiante",
    "certifiant",
    "diplomante",
    "diplomant",
    "cursus",
)

_STRONG_THRESHOLD = 2


def _normalize(text: str) -> str:
    """Minuscule + sans accents, pour des marqueurs robustes (« diplômante » → « diplomante »)."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _contains_word(haystack: str, needle: str) -> bool:
    """Teste la présence de ``needle`` comme mot (bornes de mot), pour ne pas sur-matcher.

    Évite qu'un « poe » accolé (ou qu'une sous-chaîne fortuite) ne déclenche un marqueur.
    """
    return re.search(rf"\b{re.escape(needle)}\b", haystack) is not None


def classify_kind(title: str, text: str) -> str:
    """Classe l'offre en ``formation`` ou ``emploi`` à partir du titre et du texte brut.

    ``formation`` si un marqueur de titre est présent, ou si le texte porte au moins
    ``_STRONG_THRESHOLD`` marqueurs structurels forts distincts ; ``emploi`` sinon
    (défaut prudent : on ne requalifie que sur un signal explicite).
    """
    normalized_title = _normalize(title)
    if any(_contains_word(normalized_title, marker) for marker in _TITLE_MARKERS):
        return FORMATION

    full = _normalize(f"{title}\n{text}")
    hits = {marker for marker in _STRONG_MARKERS if _contains_word(full, marker)}
    return FORMATION if len(hits) >= _STRONG_THRESHOLD else EMPLOI


def resolve_kind(llm_kind: str | None, title: str, text: str) -> str:
    """Type retenu à l'intake : proposition du LLM, corrigée par l'heuristique.

    Le LLM de normalisation propose un type (``llm_kind``, enum contraint) ; mais le petit
    modèle local classe parfois à tort une formation comme un emploi (titre trompeur, ex.
    « Ingénieur Test certifié ISTQB » qui est en réalité une POE). L'heuristique **prime donc
    sur un signal explicite de formation** (filet déterministe) ; à défaut, on fait confiance
    au LLM (repli ``emploi`` si la valeur est absente ou hors enum).
    """
    if classify_kind(title, text) == FORMATION:
        return FORMATION
    return llm_kind if llm_kind in OFFER_KINDS else DEFAULT_KIND
