"""Conversion d'une offre d'ATS (JSON brut) en ``RawOffer`` (OPP-226, RG-16 à RG-18).

Le texte envoyé à l'analyse reprend titre, entreprise, lieu, type de contrat et la description
**complète** en texte brut ; l'URL est le lien public de l'offre (clé de dédoublonnage côté
socle) ; la provenance est le nom de l'ATS (``greenhouse`` / ``lever``).

- Greenhouse (``content=true``) : ``title``, ``company_name``, ``location.name``,
  ``departments``, ``content`` (HTML **échappé** : déséchappé puis converti en texte),
  ``absolute_url``.
- Lever : ``text``, ``categories`` (lieu, ``commitment``, équipe), ``descriptionPlain``,
  ``lists`` (titre + contenu HTML), ``additionalPlain``, ``hostedUrl``. Lever ne donne pas le
  nom de l'entreprise : on reprend l'identifiant saisi (ex. ``swile``).
"""

from __future__ import annotations

import html

from app.ats_company import GREENHOUSE, AtsCompany
from app.html_text import html_to_text
from app.offer_source import RawOffer
from app.source_support import assemble_raw_text


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _with_team(team: str, description: str) -> str:
    """Préfixe la description de l'équipe/département quand l'ATS le fournit."""
    blocks = [f"Équipe : {team}" if team else "", description]
    return "\n\n".join(block for block in blocks if block)


def _greenhouse(company: AtsCompany, job: dict) -> RawOffer:
    location = job.get("location") or {}
    departments = job.get("departments") or []
    names = (_text(dept.get("name")) for dept in departments if isinstance(dept, dict))
    team = ", ".join(name for name in names if name)
    description = html_to_text(html.unescape(_text(job.get("content"))))
    raw_text = assemble_raw_text(
        title=_text(job.get("title")),
        company=_text(job.get("company_name")) or company.slug,
        location=_text(location.get("name")) if isinstance(location, dict) else "",
        contract="",
        description=_with_team(team, description),
    )
    return RawOffer(source=GREENHOUSE, raw_text=raw_text, url=_text(job.get("absolute_url")))


def _lever_lists(lists: object) -> str:
    if not isinstance(lists, list):
        return ""
    blocks = []
    for item in lists:
        if not isinstance(item, dict):
            continue
        lines = [_text(item.get("text")), html_to_text(_text(item.get("content")))]
        block = "\n".join(line for line in lines if line)
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _lever(company: AtsCompany, posting: dict) -> RawOffer:
    categories = posting.get("categories") or {}
    if not isinstance(categories, dict):
        categories = {}
    description = "\n\n".join(
        block
        for block in (
            _text(posting.get("descriptionPlain")),
            _lever_lists(posting.get("lists")),
            _text(posting.get("additionalPlain")),
        )
        if block
    )
    raw_text = assemble_raw_text(
        title=_text(posting.get("text")),
        company=company.slug,
        location=_text(categories.get("location")),
        contract=_text(categories.get("commitment")),
        description=_with_team(_text(categories.get("team")), description),
    )
    return RawOffer(source=company.ats, raw_text=raw_text, url=_text(posting.get("hostedUrl")))


def to_raw_offer(company: AtsCompany, job: dict) -> RawOffer:
    """``RawOffer`` d'une offre brute de l'ATS de ``company``."""
    if company.ats == GREENHOUSE:
        return _greenhouse(company, job)
    return _lever(company, job)
