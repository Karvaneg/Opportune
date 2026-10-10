# Environnement Docker de la stack cible Python (V2, OPP-071).
# Image minimale : installe le projet et ses dépendances de dev (pytest), puis lance
# les tests par défaut — de quoi valider l'environnement de bout en bout. Aucune
# brique métier ni service externe (SQLite/Ollama) : ceux-ci viendront avec
# OPP-072 / OPP-073.
FROM python:3.11-slim

# Sorties Python non bufferisées + pas de fichiers .pyc (logs lisibles en conteneur).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 1) Config seule d'abord : maximise le cache de couches (réinstalle les deps
#    uniquement quand pyproject change, pas à chaque modification de code).
COPY pyproject.toml ./
COPY src ./src
# `scrape` inclus pour que les tests d'extraction HTML (OPP-148) s'exécutent en CI/Docker
# plutôt que d'être sautés (importorskip bs4) ; le cœur métier reste sans dépendance.
RUN pip install --no-cache-dir -e ".[dev,scrape]"

# 2) Tests (copiés après l'install ; montés en volume en dev via docker-compose).
COPY tests ./tests

# Par défaut : exécuter la suite de tests (preuve que l'environnement fonctionne).
CMD ["pytest"]
