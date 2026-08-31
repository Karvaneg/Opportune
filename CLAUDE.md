<!-- init-ai-workspace:begin -->
## Workflow IA — Contexte projet

- **Stack détectée :** Non détectée (fallback shell)
- **Commande de test :** Non détecté
- **Script de contexte :** `scripts/generate-ai-context.sh`
- **Fichier de contexte :** `.claude/skills/project-context.md`

**Règle de fraîcheur :** si `.claude/skills/project-context.md` est absent ou date de plus de 24h, exécute `bash scripts/generate-ai-context.sh` avant toute autre action.

Ce fichier est un point de départ minimal — destiné à être enrichi au fil du temps avec les règles spécifiques au projet (typage, architecture, tests, etc.), en dehors de cette zone gérée par le skill.
<!-- init-ai-workspace:end -->
