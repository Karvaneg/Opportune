"""Filtre « poste recherché » des offres d'ATS (OPP-226, RG-11).

Une entreprise ciblée publie souvent des dizaines d'offres sans rapport avec le poste visé, et
chaque offre émise passe ensuite par le LLM local (plusieurs secondes par offre). Quand
l'utilisateur saisit un poste, on écarte **avant** l'analyse les offres dont l'intitulé ne le
contient pas. Logique pure.

Règle de correspondance : chaque mot du poste saisi doit être le **début d'un mot** de
l'intitulé, sans tenir compte de la casse ni des accents. « data analyst » garde « Senior Data
Analyst (H/F) », « dev » garde « Développeur », mais « IA » ne garde pas « Commercial » (le mot
ne commence pas par « ia »). Un poste vide ne filtre rien : on garde alors toutes les offres.

Limite connue : seuls lettres et chiffres comptent, donc « C++ » se réduit à « c » et garde
aussi « Développeur C# ».
"""

from __future__ import annotations

import re

from app.ats_company import GREENHOUSE
from app.offer_normalization import strip_accents

_WORD = re.compile(r"\w+")


def _normalize(text: str) -> str:
    return strip_accents(text).casefold()


def job_title(ats: str, job: dict) -> str:
    """Intitulé brut d'une offre d'ATS : ``title`` (Greenhouse) ou ``text`` (Lever)."""
    value = job.get("title") if ats == GREENHOUSE else job.get("text")
    return value if isinstance(value, str) else ""


def matches_title(query: str, title: str) -> bool:
    """Vrai si chaque mot de ``query`` commence un mot de ``title`` (casse et accents ignorés)."""
    words = _WORD.findall(_normalize(query))
    if not words:
        return True
    title_words = _WORD.findall(_normalize(title))
    return all(
        any(title_word.startswith(word) for title_word in title_words) for word in words
    )
