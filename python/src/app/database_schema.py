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
from app.submission_store import SubmissionStore
from hermes.run_store import RunStore

_STORES = (
    OfferStore,
    ProfileStore,
    DecisionStore,
    LetterStore,
    ApplicationActionStore,
    OutboundMessageActionStore,
    SubmissionStore,
    ApplicationTrackingStore,
    CandidateRegistry,
    RunStore,
    # Après ``OfferStore`` et ``CandidateRegistry`` : sur une archive antérieure à OPP-186, la
    # création de la table de liens rattache les offres importées aux recherches importées.
    CandidateOfferStore,
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Crée les tables manquantes et ajoute les colonnes manquantes de tous les dépôts."""
    for store in _STORES:
        store(conn)
