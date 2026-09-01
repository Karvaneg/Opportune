# Vision & stack cible

> ⚠️ Ce document décrit la **vision produit** et la **stack cible** d'Opportune.
> Il ne reflète pas l'implémentation actuelle du dépôt (Node.js, sans dépendances
> hors `@notionhq/client` + `dotenv`, stockage en fichiers JSON). C'est une cible
> vers laquelle le projet peut évoluer, pas un état des lieux.

## Objectif

Un **assistant de recherche d'opportunités**, capable de proposer aussi bien un
**CDI** qu'une **mission freelance**, sans obliger à choisir immédiatement entre
les deux.

## Flux cible

```
offre sélectionnée → dossier personnalisé → validation → envoi manuel ou semi-automatique
```

## Stack adaptée

| Brique | Rôle |
|---|---|
| **Ministral + Ollama** | Analyse et rédaction |
| **Anthropic** | Contrôle qualité des candidatures importantes |
| **Kyutai** | Commandes vocales et notes vocales |
| **Discord** | Interface de validation |
| **SQLite** | Suivi des offres et candidatures |
| **Python / Docker / WSL** | Orchestration |
