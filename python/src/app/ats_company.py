"""Entreprise ciblée sur un ATS, déduite de l'URL de sa page carrière (OPP-226).

Un ATS (logiciel de recrutement) publie les offres d'une entreprise sur une page carrière dont
l'URL porte l'**identifiant** de l'entreprise chez cet ATS. L'utilisatrice colle cette URL dans
les Réglages ; ce module en déduit ``(ATS, identifiant)``. Logique pure, sans réseau.

Formats reconnus (RG-1) :

- Lever : ``jobs.lever.co/{site}`` (API mondiale) et ``jobs.eu.lever.co/{site}`` (API EU) ;
- Greenhouse : ``boards.greenhouse.io/{token}``, ``job-boards.greenhouse.io/{token}`` et leurs
  variantes EU ``boards.eu.greenhouse.io`` / ``job-boards.eu.greenhouse.io``. Les boards EU sont
  servis par la **même** API que les autres (vérifié le 2026-11-04) : seule l'URL publique change,
  d'où ``eu`` retenu pour réafficher la bonne URL mais ignoré dans la clé d'unicité ;
- Greenhouse intégré à un site : ``boards.greenhouse.io/embed/job_board?for={token}``.

L'identifiant est le premier segment du chemin (ou le paramètre ``for`` d'une URL ``embed``) ; le
reste (``/jobs/123``, paramètres, fragment, slash final) est ignoré, et le schéma
``http``/``https`` est indifférent.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

GREENHOUSE = "greenhouse"
LEVER = "lever"

# Hôte de page carrière → (ATS, hébergement EU). Seule Lever a une API distincte pour l'EU ; pour
# Greenhouse, le drapeau ne sert qu'à réafficher l'URL publique EU.
_HOSTS: dict[str, tuple[str, bool]] = {
    "jobs.lever.co": (LEVER, False),
    "jobs.eu.lever.co": (LEVER, True),
    "boards.greenhouse.io": (GREENHOUSE, False),
    "job-boards.greenhouse.io": (GREENHOUSE, False),
    "boards.eu.greenhouse.io": (GREENHOUSE, True),
    "job-boards.eu.greenhouse.io": (GREENHOUSE, True),
}

# Formats affichés dans les messages d'erreur (RG-2).
SUPPORTED_FORMATS = (
    "jobs.lever.co/{entreprise}",
    "jobs.eu.lever.co/{entreprise}",
    "boards.greenhouse.io/{entreprise}",
    "job-boards.greenhouse.io/{entreprise}",
    "boards.eu.greenhouse.io/{entreprise}",
    "job-boards.eu.greenhouse.io/{entreprise}",
    "boards.greenhouse.io/embed/job_board?for={entreprise}",
)


class AtsUrlError(ValueError):
    """L'URL ne correspond à aucune page carrière d'ATS reconnue."""


@dataclass(frozen=True)
class AtsCompany:
    """Une entreprise ciblée : son ATS, son identifiant chez lui et son hébergement EU."""

    ats: str
    slug: str
    eu: bool = False

    @property
    def key(self) -> tuple[str, str, bool]:
        """Clé d'unicité (RG-5) : l'identifiant est comparé sans tenir compte de la casse.

        Pour Greenhouse, ``eu`` est ignoré : un board EU et un board non EU de même identifiant
        sont servis par la même API, donc c'est la même entreprise.
        """
        return (self.ats, self.slug.casefold(), self.eu and self.ats == LEVER)

    @property
    def career_url(self) -> str:
        """URL canonique de la page carrière, réaffichée dans les Réglages."""
        if self.ats == LEVER:
            host = "jobs.eu.lever.co" if self.eu else "jobs.lever.co"
        else:
            host = "job-boards.eu.greenhouse.io" if self.eu else "job-boards.greenhouse.io"
        return f"https://{host}/{self.slug}"


def parse_career_url(raw: str) -> AtsCompany:
    """Déduit l'entreprise ciblée d'une URL de page carrière ; lève ``AtsUrlError`` sinon.

    Tolère l'absence de schéma (``jobs.lever.co/swile``) : c'est ce que l'on copie souvent
    depuis la barre d'adresse.
    """
    text = (raw or "").strip()
    if not text:
        raise AtsUrlError("ligne vide")
    if "://" not in text:
        text = f"https://{text}"
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise AtsUrlError(f"URL non reconnue : {raw.strip()}")
    host = (parts.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    known = _HOSTS.get(host)
    segments = [segment for segment in parts.path.split("/") if segment]
    if known is None or not segments:
        raise AtsUrlError(f"URL non reconnue : {raw.strip()}")
    ats, eu = known
    slug = segments[0]
    if ats == GREENHOUSE and slug.casefold() == "embed":
        # Board intégré à un site : l'identifiant est dans ``?for=`` (``/embed/job_board?for=acme``).
        slug = (parse_qs(parts.query).get("for") or [""])[0].strip()
        if not slug:
            raise AtsUrlError(f"URL non reconnue : {raw.strip()}")
    return AtsCompany(ats=ats, slug=slug, eu=eu)
