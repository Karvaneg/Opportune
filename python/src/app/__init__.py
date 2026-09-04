"""Opportune — cœur métier de la stack V2 (Python).

Ce package porte le métier de la V2 : ingestion et analyse d'offres, profil candidat,
matching, scoring, recommandation, décision et sa validation humaine, actions sensibles,
plus les accès techniques (SQLite via ``db``, LLM via ``llm``/``llm_client``,
authentification via ``auth``). L'orchestration vit dans ``hermes`` et l'exposition HTTP
dans ``api``. ``version`` et ``healthcheck`` restent le point de contrôle minimal de
l'environnement.
"""

__version__ = "1.0.0"


def healthcheck() -> str:
    """Statut minimal : prouve que le package s'importe et s'exécute."""
    return "ok"
