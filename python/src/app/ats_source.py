"""Source d'offres « entreprises ciblées » via leurs ATS, port ``SourceOffres`` (OPP-226).

Adaptateur mince entre le client d'ATS (``ats_client``) et le socle de collecte
(``offer_collection``) : pour chaque entreprise ciblée, une requête liste ses offres publiées,
on ne garde que celles situées en France (``ats_location``) et on émet des ``RawOffer``
(``ats_offer``). Aucune analyse ni persistance ici : le socle dédoublonne avant le LLM.

Règles portées par la source :

- **Ordre et plafond (RG-15).** Les entreprises sont parcourues dans l'ordre de la liste ;
  ``max_offers`` borne le total émis, toutes entreprises confondues.
- **Filtre France (RG-12).** Une offre hors France n'est pas émise ; elle est comptée dans
  ``excluded`` (ni doublon, ni échec).
- **Filtre poste (RG-11).** Si un poste est saisi, une offre en France dont l'intitulé ne le
  contient pas n'est pas émise ; elle est comptée dans ``off_target``. Poste vide : aucun filtre.
- **Échec par entreprise (RG-20, RG-21).** Une entreprise qui échoue (404, 429, réseau, réponse
  illisible) est consignée dans ``warnings`` et la passe continue avec les suivantes. La source
  ne lève que si **toutes** les entreprises ont échoué : le socle range alors l'erreur en
  ``source_error``.
- **Sobriété (RG-21).** Requêtes séquentielles, une seule par entreprise.
"""

from __future__ import annotations

from typing import Iterable, Iterator

from app.ats_client import AtsClient, AtsError
from app.ats_company import AtsCompany
from app.ats_location import is_in_france
from app.ats_offer import to_raw_offer
from app.ats_title_filter import job_title, matches_title
from app.offer_source import RawOffer

# Plafond d'offres par défaut d'une passe (même ordre de grandeur que la source RSS).
DEFAULT_MAX_OFFERS = 500


class AtsSource:
    """Source ``SourceOffres`` qui interroge l'ATS de chaque entreprise ciblée."""

    def __init__(
        self,
        companies: Iterable[AtsCompany],
        *,
        client: AtsClient,
        max_offers: int = DEFAULT_MAX_OFFERS,
        title_query: str = "",
    ) -> None:
        self._companies = list(companies)
        self._client = client
        self._max_offers = max(1, max_offers)
        self._title_query = title_query
        # Compteurs de bilan, lus par l'appelant une fois la passe terminée.
        self.excluded = 0
        self.off_target = 0
        self.warnings: list[str] = []

    def fetch(self) -> Iterator[RawOffer]:
        """Itère les offres en France de chaque entreprise, jusqu'au plafond ``max_offers``."""
        emitted = 0
        failed = 0
        for company in self._companies:
            if emitted >= self._max_offers:
                break
            try:
                jobs = self._client.list_jobs(company)
            except AtsError as exc:
                failed += 1
                self.warnings.append(str(exc))
                continue
            for job in jobs:
                if emitted >= self._max_offers:
                    break
                if not is_in_france(company.ats, job):
                    self.excluded += 1
                    continue
                if not matches_title(self._title_query, job_title(company.ats, job)):
                    self.off_target += 1
                    continue
                yield to_raw_offer(company, job)
                emitted += 1
        if self._companies and failed == len(self._companies):
            raise AtsError(
                "aucune entreprise ciblée n'a pu être interrogée : " + " ; ".join(self.warnings)
            )


def build_ats_source(
    companies: Iterable[AtsCompany],
    *,
    max_offers: int = DEFAULT_MAX_OFFERS,
    title_query: str = "",
) -> AtsSource:
    """Assemble une ``AtsSource`` avec le transport HTTP réel (câblage prod)."""
    return AtsSource(
        companies,
        client=AtsClient(),
        max_offers=max_offers,
        title_query=title_query,
    )
