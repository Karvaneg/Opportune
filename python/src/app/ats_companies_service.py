"""Mise à jour des entreprises ciblées depuis les Réglages (OPP-226, RG-1 à RG-7).

L'utilisatrice colle une URL de page carrière par ligne. Ce service :

1. **Tout supprimer (RG-6)** si aucune ligne n'est saisie ;
2. **lit chaque ligne** (``parse_career_url``) et refuse l'ensemble si une seule est invalide,
   en citant chaque ligne fautive et les formats acceptés (RG-1, RG-2 : tout ou rien) ;
3. **dédoublonne** les entreprises collées sous deux formes d'URL (RG-5) ;
4. applique le **plafond** de ``MAX_COMPANIES`` (RG-7) ;
5. **vérifie** auprès de l'ATS chaque entreprise qui n'était pas déjà enregistrée (RG-3) : 404 →
   refus « introuvable », panne réseau → refus « vérification impossible ». Une entreprise sans
   offre est acceptée (RG-4) ; on rend son nombre d'offres en France. Les vérifications sont
   **séquentielles** (RG-21 : appels sobres, jamais plusieurs requêtes à la fois vers un ATS) et
   s'arrêtent à la première erreur ;
6. enregistre la liste.

Les erreurs de saisie lèvent ``ValueError`` (400 côté API) ; l'impossibilité de vérifier lève
``AtsVerificationUnavailable`` (502 côté API) ; l'échec d'écriture du fichier lève
``AtsCompaniesWriteError`` (500 côté API). Cette dernière est distincte d'``OSError`` pour qu'une
panne réseau ne soit jamais présentée comme une erreur d'enregistrement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.ats_client import ATS_LABELS, AtsClient, AtsError, AtsNotFoundError
from app.ats_companies_store import AtsCompaniesStore
from app.ats_company import SUPPORTED_FORMATS, AtsCompany, AtsUrlError, parse_career_url
from app.ats_location import is_in_france

MAX_COMPANIES = 50


class AtsVerificationUnavailable(Exception):
    """Un ATS n'a pas pu être joint : on n'enregistre pas une entreprise non vérifiée (RG-3)."""


class AtsCompaniesWriteError(Exception):
    """Le fichier des entreprises ciblées n'a pas pu être écrit (disque plein, droits...)."""


@dataclass(frozen=True)
class CompanyCheck:
    """Entreprise enregistrée ; ``offers_in_france`` n'est connu que juste après vérification."""

    company: AtsCompany
    offers_in_france: int | None = None


def _parse_lines(lines: list[str]) -> list[AtsCompany]:
    companies: list[AtsCompany] = []
    invalid: list[str] = []
    for line in lines:
        try:
            companies.append(parse_career_url(line))
        except AtsUrlError:
            invalid.append(line.strip())
    if invalid:
        raise ValueError(
            "URL non reconnue : "
            + ", ".join(invalid)
            + ". Formats acceptés : "
            + ", ".join(SUPPORTED_FORMATS)
        )
    return companies


def _dedupe(companies: list[AtsCompany]) -> list[AtsCompany]:
    seen: set[tuple[str, str, bool]] = set()
    unique = []
    for company in companies:
        if company.key not in seen:
            seen.add(company.key)
            unique.append(company)
    return unique


def _verify(company: AtsCompany, client: AtsClient) -> int:
    """Nombre d'offres en France de l'entreprise ; lève si l'ATS l'ignore ou est injoignable."""
    label = ATS_LABELS.get(company.ats, company.ats)
    try:
        # Liste allégée : on ne fait que compter, inutile de télécharger les descriptions.
        jobs = client.list_jobs(company, with_content=False)
    except AtsNotFoundError as exc:
        raise ValueError(f"entreprise introuvable sur {label} : {company.career_url}") from exc
    except AtsError as exc:
        raise AtsVerificationUnavailable(
            f"vérification impossible auprès de {label} ({company.slug}), réessaie plus tard"
        ) from exc
    return sum(1 for job in jobs if is_in_france(company.ats, job))


def _write(operation: Callable[[], None]) -> None:
    """Exécute une écriture du store en traduisant ``OSError`` en ``AtsCompaniesWriteError``."""
    try:
        operation()
    except OSError as exc:
        raise AtsCompaniesWriteError(str(exc)) from exc


def _verify_all(
    companies: list[AtsCompany], client: AtsClient
) -> dict[tuple[str, str, bool], int]:
    """Vérifie les entreprises une par une, dans l'ordre de saisie (RG-21).

    La première erreur remonte aussitôt : les entreprises suivantes ne sont pas interrogées.
    """
    return {company.key: _verify(company, client) for company in companies}


def update_companies(
    lines: list[object], *, store: AtsCompaniesStore, client: AtsClient
) -> list[CompanyCheck]:
    """Valide, vérifie et enregistre la liste saisie ; rend les entreprises retenues."""
    if any(not isinstance(line, str) for line in lines):
        # Une entrée non textuelle (``null``, nombre…) est une requête malformée : la refuser
        # plutôt que l'ignorer, sinon ``[null]`` passerait pour « tout supprimer ».
        raise ValueError("companies doit être une liste d'URLs (texte)")
    entered = [line for line in lines if line.strip()]
    if not entered:
        _write(store.clear)
        return []
    companies = _dedupe(_parse_lines(entered))
    if len(companies) > MAX_COMPANIES:
        raise ValueError(f"{MAX_COMPANIES} entreprises maximum ({len(companies)} saisies)")
    known = {company.key for company in store.load()}
    to_verify = [company for company in companies if company.key not in known]
    offers_in_france = _verify_all(to_verify, client)
    checks = [CompanyCheck(company, offers_in_france.get(company.key)) for company in companies]
    _write(lambda: store.save(companies))
    return checks
