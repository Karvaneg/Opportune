"""Stockage local des entreprises ciblées sur un ATS (OPP-226).

Même principe que les flux RSS (``rss_feeds_store``) : un fichier JSON dans le **dossier de
données de l'app** (hors dépôt, local-first), un par espace pour que « Mon espace » et « Démo »
ne partagent pas leurs réglages (RG-8). Ce ne sont pas des secrets (RG-9).

Ce module ne fait que lire et écrire : la validation des URLs et la vérification auprès des ATS
relèvent de ``ats_companies_service``. La lecture est tolérante (fichier absent, illisible ou
corrompu → liste vide), comme les autres stores de réglages.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ats_company import GREENHOUSE, LEVER, AtsCompany
from app.json_file_store import load_json_object
from app.paths import user_data_dir

_FILENAME = "ats_companies.json"


def default_ats_companies_path(data_dir: Path | None = None) -> Path:
    """Chemin du fichier des entreprises ciblées dans un dossier de données (un par espace)."""
    return (data_dir or user_data_dir()) / _FILENAME


def _parse(entry: object) -> AtsCompany | None:
    if not isinstance(entry, dict):
        return None
    ats = entry.get("ats")
    slug = entry.get("slug")
    if ats not in (GREENHOUSE, LEVER) or not isinstance(slug, str) or not slug.strip():
        return None
    return AtsCompany(ats=ats, slug=slug.strip(), eu=entry.get("eu") is True)


class AtsCompaniesStore:
    """Lit/écrit la liste des entreprises ciblées dans un fichier JSON local."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[AtsCompany]:
        """Entreprises enregistrées (ordre conservé), ou liste vide si rien d'exploitable."""
        data = load_json_object(self._path)
        if data is None or not isinstance(data.get("companies"), list):
            return []
        return [company for company in map(_parse, data["companies"]) if company is not None]

    def save(self, companies: list[AtsCompany]) -> None:
        """Remplace la liste enregistrée ; crée le dossier parent au besoin (1er lancement)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"ats": c.ats, "slug": c.slug, "eu": c.eu} for c in companies]
        self._path.write_text(json.dumps({"companies": payload}), encoding="utf-8")

    def clear(self) -> None:
        """Supprime la liste (le fichier) ; sans effet si elle est déjà absente."""
        self._path.unlink(missing_ok=True)
