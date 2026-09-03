"""Configuration produit (V2).

Regroupe les paramètres métier ajustables au niveau produit — aujourd'hui les seuils
de recommandation (score → action). Les modules consommateurs les importent comme
valeurs par défaut, tout en gardant la possibilité de les surcharger par appel.
"""

from __future__ import annotations

# Seuils de recommandation (bornes basses incluses) : score ≥ high → postuler,
# score ≥ medium → à étudier, sinon → ignorer.
RECOMMENDATION_HIGH = 75
RECOMMENDATION_MEDIUM = 50
