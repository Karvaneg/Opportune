# Design system Opportune

Les jetons de marque et la façon dont ils s'appliquent au frontend. Ce dossier est la **copie
intégrée** de la charte ; la source de référence (doc de marque complète, logos, composants) vit
dans `opportune-charte/` (hors dépôt pour l'instant).

Opportune est une application locale et privée : sérieuse et rigoureuse, mais chaleureuse — un
**copilote de confiance**, pas un outil corporate. Le design suit ce même équilibre.

## La signature : le toupet de Kairos

Les Grecs avaient deux mots pour le temps : *chronos*, le temps qui s'écoule, et *kairos*, le
moment opportun. Kairos était un jeune dieu qui passait en courant, le crâne rasé à l'arrière, avec
**une seule mèche sur le front** : il fallait l'attraper par cette mèche au passage, sinon l'occasion
était perdue. C'est l'origine de « saisir l'occasion aux cheveux ».

La signature d'Opportune, c'est cette mèche. Le trait du **O** se décolle de l'anneau, s'envole vers
l'avant et s'enroule au-dessus des « pp », en indigo (`--brand`) ; le reste du mot reste en `--ink`.
L'occasion passe, Opportune aide à la saisir au bon moment — le produit en une image.

Le composant [`Logo`](../components/Logo.tsx) rend cette signature en **SVG inline lié aux jetons**
(la mèche en `var(--brand)`, le mot en `var(--ink)`), donc elle suit le thème. Hauteur de référence
32px en barre de navigation, jamais sous 20px (en dessous la mèche devient illisible : utiliser le
favicon seul).

## Les fichiers

| Fichier | Rôle |
|---|---|
| `tokens.css` | **Ce que l'app charge.** Variables CSS : couleurs clair + sombre, typo, espacements, rayons, tailles de logo. |
| `tokens.json` | Source de référence des mêmes valeurs (documentée, ratios WCAG). **Pas importé** par le code. |

⚠️ **Aucune génération automatique** entre les deux : toute modification d'un jeton doit être
reportée **à la main** dans l'autre fichier (cf. `_note` en tête de `tokens.json`). Les jetons de
survol `--success-strong` / `--warning-strong` / `--danger-strong` ont été ajoutés **localement**
(absents de la charte amont) ; penser à les y reporter si on veut réaligner la source.

## Les jetons

Couleurs **sémantiques**, jamais des noms de teinte — on écrit l'intention, pas la nuance :

- **Neutres** : `surface` / `surface-raised` (fonds), `ink` / `ink-muted` (texte), `border` /
  `border-strong` (contours).
- **Marque** : `brand` (LA couleur de marque — mèche, liens, bouton principal, focus),
  `brand-strong` (survol), `on-brand` (texte posé sur un fond `brand`).
- **Sémantiques** : `success` / `warning` / `danger` (+ `-text` pour le texte lisible sur fond clair,
  `-strong` pour le survol). **Jamais utilisées comme couleur de marque.**

Chaque jeton a une valeur claire et une valeur sombre ; le code ne manipule que le nom.

## Intégration (Tailwind v4)

[`../index.css`](../index.css) importe `tokens.css` puis mappe les jetons sur le thème Tailwind
avec `@theme inline` :

```css
@import "./styles/tokens.css";
@theme inline {
  --color-surface: var(--surface);
  --color-ink: var(--ink);
  --color-brand: var(--brand);
  /* … */
}
```

`inline` fait émettre `var(--surface)` directement dans les utilitaires, si bien que `bg-surface`,
`text-ink`, `bg-brand`, `border-border`… **suivent la bascule clair/sombre sans variante `dark:`**.
Opacités via la syntaxe standard (`bg-brand/10`, `bg-ink/5`).

**Règle** : pas de couleur Tailwind en dur (`bg-indigo-600`, `text-slate-900`…) dans les composants —
toujours un utilitaire sémantique.

### Typographie

L'échelle de la charte est exposée en classes `.opp-display` → `.opp-label` (préfixées pour éviter
toute collision). La pile de police est `--font-sans` (système, comme l'appli).

## Thème clair / sombre

Un attribut `data-theme` est **toujours** présent sur `<html>` — il n'y a donc qu'un seul bloc par
thème dans `tokens.css` (pas de `@media prefers-color-scheme` à tenir en double) :

- **Au boot** : un script inline dans `index.html` lit `localStorage["opportune.theme"]`. Valeur
  `"light"`/`"dark"` → posée telle quelle ; sinon (`"auto"`, clé absente) → résolue via
  `prefers-color-scheme`. Appliqué **avant le rendu** pour éviter tout flash.
- **Au clic** : le [`ThemeToggle`](../components/ThemeToggle.tsx) cycle `auto → clair → sombre`,
  persiste le choix (clé absente = auto) et, en mode auto, suit les bascules système en direct.

## Ton

Précis d'abord, avec un brin d'espièglerie. On parle comme un copilote : « Cette offre coche 8 de
vos 10 critères », pas « Score de pertinence : 80 % ». Un clin d'œil au bon moment (« elle vient de
sortir, c'est le moment »), jamais de jargon RH ni de promesses : Opportune aide à décider, elle ne
décide pas.
