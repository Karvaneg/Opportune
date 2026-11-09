"""Mise à niveau du schéma SQLite d'un espace (OPP-232).

Chaque dépôt crée ses tables et ajoute ses colonnes manquantes **à sa construction**
(``CREATE TABLE IF NOT EXISTS`` puis ``ALTER TABLE`` idempotents). Au démarrage, c'est
``assemble_api`` qui les construit. Quand la base est remplacée à chaud (import de données), son
schéma peut dater d'une version antérieure d'Opportune : on reconstruit donc chaque dépôt sur la
connexion pour rejouer ces mises à niveau, sans attendre un redémarrage.
"""

from __future__ import annotations

import sqlite3

from app.action_store import ApplicationActionStore, OutboundMessageActionStore
from app.application_tracking_store import ApplicationTrackingStore
from app.candidate_offer_store import CandidateOfferStore
from app.candidate_registry import CandidateRegistry
from app.decision_store import DecisionStore
from app.letter_store import LetterStore
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from hermes.run_store import RunStore

_STORES = (
    OfferStore,
    ProfileStore,
    DecisionStore,
    LetterStore,
    ApplicationActionStore,
    OutboundMessageActionStore,
    ApplicationTrackingStore,
    CandidateRegistry,
    RunStore,
    # Après ``OfferStore`` et ``CandidateRegistry`` : sur une archive antérieure à OPP-186, la
    # création de la table de liens rattache les offres importées aux recherches importées.
    CandidateOfferStore,
)


# Tables d'anciennes versions que plus aucun dépôt ne lit : ``submissions`` suivait les cartes
# de revue postées sur Discord (OPP-131), chemin supprimé en OPP-243.
_OBSOLETE_TABLES = ("submissions",)


def drop_obsolete_tables(conn: sqlite3.Connection) -> None:
    """Supprime les tables obsolètes (idempotent : sans effet si elles sont absentes)."""
    for table in _OBSOLETE_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Met le schéma à niveau : tables et colonnes manquantes créées, tables obsolètes supprimées."""
    for store in _STORES:
        store(conn)
    drop_obsolete_tables(conn)
