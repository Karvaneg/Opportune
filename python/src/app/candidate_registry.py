"""Registre du périmètre : les candidats (« recherches ») connus de l'espace (V2, OPP-183/184).

Jusqu'ici le périmètre (``owned_candidates``) était un ``frozenset`` figé au boot depuis la
variable d'environnement ``OPPORTUNE_API_CANDIDATES`` (cf. ``api.server``). OPP-183 le rend
**dynamique et stocké en base** : ce registre liste les candidats de l'espace courant, et l'auth
en dérive le périmètre à chaque requête. OPP-184 lui ajoute un **libellé** (nommer une recherche)
et la **création / renommage à chaud** depuis l'app — l'env n'est plus l'unique moyen d'enrôler.

Un candidat du registre existe **indépendamment de son profil** : il peut être enrôlé sans CV
encore (état « nouveau profil »), ce qui laisse le cockpit afficher le guide d'accueil plutôt
qu'un « aucun candidat ». Périmètre et profil sont donc deux notions distinctes — c'est ce qui
permet au « repartir de zéro » de la démo de garder un slot vide à renseigner.

Neutre de vocabulaire **en interne** : on parle de *candidat* ici (clé technique partagée avec
profils / décisions / offres). Côté produit, c'est une « recherche » (``label``) — le renommage
transversal « candidat » → « recherche » dans l'UI est l'objet de la dernière tranche d'OPP-184.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Search:
    """Une recherche du périmètre : son id technique (clé partagée) et son libellé produit."""

    id: str
    label: str


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT ''
)
"""

# Un seul INSERT, deux variantes : ``_INSERT`` lève sur collision d'id (``create`` s'en sert pour
# régénérer), ``_INSERT_OR_IGNORE`` l'avale (enrôlement idempotent de ``add`` / ``ensure``).
_INSERT = "INSERT INTO candidates (id, created_at, label) VALUES (?, ?, ?)"
_INSERT_OR_IGNORE = _INSERT + " ON CONFLICT(id) DO NOTHING"


class CandidateRegistry:
    """Dépôt SQLite du périmètre : les candidats de l'espace, avec libellé (crée/migre sa table)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute(_CREATE_TABLE)
        self._ensure_label_column()
        self.conn.commit()

    def _ensure_label_column(self) -> None:
        """Migration douce : ajoute ``label`` aux bases antérieures à OPP-184 (table sans colonne).

        ``CREATE TABLE IF NOT EXISTS`` ne modifie pas une table déjà présente : une base créée
        sous OPP-183 n'aurait pas ``label``. On l'ajoute au besoin (idempotent) plutôt que de
        laisser les requêtes échouer. Les lignes existantes héritent du défaut ``''``.
        """
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(candidates)")}
        if "label" not in columns:
            self.conn.execute("ALTER TABLE candidates ADD COLUMN label TEXT NOT NULL DEFAULT ''")

    def list_ids(self) -> list[str]:
        """Ids du périmètre (ordre d'id) — source du ``owned_candidates`` de l'auth."""
        return [row[0] for row in self.conn.execute("SELECT id FROM candidates ORDER BY id")]

    def list(self) -> list[Search]:
        """Recherches du périmètre (id + libellé), ordonnées par id — pour le sélecteur (OPP-184)."""
        return [
            Search(id=row[0], label=row[1])
            for row in self.conn.execute("SELECT id, label FROM candidates ORDER BY id")
        ]

    def add(self, candidate_id: str, label: str = "") -> None:
        """Enrôle un candidat dans le périmètre (idempotent : réinsérer ne duplique pas).

        ``ON CONFLICT DO NOTHING`` : réinsérer un id existant **ne touche pas** son libellé
        (le re-seed démo ou le bootstrap env ne doivent pas écraser un nom donné à la main).
        """
        self.conn.execute(_INSERT_OR_IGNORE, (candidate_id, _utcnow_iso(), label.strip()))
        self.conn.commit()

    def ensure(self, candidate_ids: Iterable[str]) -> None:
        """Enrôle plusieurs candidats d'un coup (insert-or-ignore). Vides/doublons ignorés."""
        rows = [(cid, _utcnow_iso(), "") for cid in candidate_ids if cid]
        if not rows:
            return
        self.conn.executemany(_INSERT_OR_IGNORE, rows)
        self.conn.commit()

    def create(self, label: str, *, new_id: Callable[[], str] | None = None) -> Search:
        """Crée une nouvelle recherche au libellé donné, à id technique **généré** (OPP-184).

        L'id est opaque et stable (``search-<hex>``) : indépendant du libellé, il ne change pas
        au renommage — les profils / décisions / offres qui le référencent restent valides.
        ``new_id`` est injectable pour un id déterministe en test. Collision (astronomiquement
        improbable) → l'``INSERT`` lève ``IntegrityError`` sur la clé primaire et on régénère —
        pas de scan préalable du périmètre.
        """
        mint = new_id or (lambda: f"search-{uuid.uuid4().hex[:12]}")
        label = label.strip()
        while True:
            candidate_id = mint()
            try:
                self.conn.execute(_INSERT, (candidate_id, _utcnow_iso(), label))
            except sqlite3.IntegrityError:
                continue
            break
        self.conn.commit()
        return Search(id=candidate_id, label=label)

    def rename(self, candidate_id: str, label: str) -> bool:
        """Renomme une recherche (``label``). Rend ``True`` si l'id existait, ``False`` sinon.

        ``False`` laisse l'appelant répondre 404 neutre sur un id hors périmètre (anti-énumération),
        sans distinguer « inconnu » d'« absent ».
        """
        cursor = self.conn.execute(
            "UPDATE candidates SET label = ? WHERE id = ?", (label.strip(), candidate_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0
