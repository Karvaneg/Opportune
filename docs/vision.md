# Vision & stack cible

> ℹ️ Ce document décrit la **vision produit** et la **stack cible** d'Opportune.
> L'implémentation actuelle est la **V2 Python** (cœur métier, orchestrateur Hermes,
> API HTTP — bibliothèque standard, SQLite), qui réalise déjà une bonne partie de cette
> cible : scoring des offres, génération de lettre de motivation (Ollama/Ministral) et
> validation humaine via Discord (cœur composé et testé). Restent notamment en chantier
> la **collecte réelle** des offres, le **CV adapté** et le message LinkedIn, et le
> **récepteur Discord live**. L'ancienne implémentation Node.js/JSON n'a plus cours.

## Objectif

Un **assistant de recherche d'opportunités**, capable de proposer aussi bien un
**CDI** qu'une **mission freelance**, sans obliger à choisir immédiatement entre
les deux.

## Flux cible

```
offre sélectionnée → dossier personnalisé → validation → envoi manuel ou semi-automatique
```

## Stack adaptée

| Brique                    | Rôle                                          |
| ------------------------- | --------------------------------------------- |
| **Ministral + Ollama**    | Analyse et rédaction                          |
| **Anthropic**             | Contrôle qualité des candidatures importantes |
| **Kyutai**                | Commandes vocales et notes vocales            |
| **Discord**               | Interface de validation (push-to-triage, MVP) |
| **SQLite**                | Suivi des offres et candidatures              |
| **Python / Docker / WSL** | Orchestration                                 |

## Architecture élargie

```
Sources d'offres
 ├─ Sites d'emploi / API
 ├─ Plateformes freelance
 └─ Alertes e-mail / RSS
          ↓
Collecte et dédoublonnage
          ↓
Ministral : analyse + scoring
          ↓
Classification
 ├─ CDI
 ├─ Freelance
 └─ À ignorer
          ↓
Personnalisation
 ├─ CV adapté
 ├─ Lettre de motivation
 ├─ Message LinkedIn
 └─ Proposition freelance
          ↓
Validation humaine
          ↓
Candidature / suivi
```

## Priorité recommandée

Commencer par le **workflow CDI**, plus simple à cadrer :

1. Importer les offres
2. Extraire les compétences, lieu, salaire et exigences
3. Comparer avec le profil
4. Attribuer un score
5. Adapter le CV
6. Générer une lettre
7. Demander validation
8. Enregistrer la candidature et les relances

Ensuite, ajouter le **freelance** avec ses critères spécifiques :

- Budget
- Durée
- TJM
- Disponibilité
- Risque client
- Adéquation avec le portfolio
