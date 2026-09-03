"""Opportune — ossature de la stack cible Python (V2, OPP-070).

À ce stade, le package ne contient que le strict nécessaire pour valider
l'environnement : version et test de fumée. Aucune logique métier n'est encore
portée depuis la base Node.js (cf. OPP-071 Docker/WSL, OPP-072 SQLite,
OPP-073 Ollama, puis le pivot fonctionnel).
"""

__version__ = "0.1.0"


def healthcheck() -> str:
    """Statut minimal : prouve que le package s'importe et s'exécute."""
    return "ok"
