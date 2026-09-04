# ADR 0002 — Authentification frontend : jeton en localStorage validé par `/me`

- **Statut** : Accepté — **en vigueur**
- **Date** : 2026-09-04
- **Contexte ticket** : OPP-100 / OPP-103 (Epic E9 — Consultation Hermes) ; OPP-102 différé
- **Décideurs** : équipe Opportune

## Contexte

Le frontend de consultation d'Hermes (React/Vite, cf. `frontend/`) doit authentifier
l'utilisateur auprès de l'API Python. L'API attend un jeton porteur
(`Authorization: Bearer <token>`) et n'expose **pas** de flux de session (pas de cookie
de session, pas d'OAuth, pas de refresh token) : c'est un dashboard **interne**, à faible
exposition, au périmètre restreint (un porteur = ses candidats possédés).

Deux besoins concrets se posaient :

1. **Persistance** — ne pas redemander le jeton à chaque rechargement de page.
2. **Validation** — ne pas ouvrir la coquille applicative sur un jeton invalide (la
   première version d'OPP-100 se contentait de la *présence* d'un jeton ; un mauvais
   jeton ouvrait l'UI et ne échouait qu'au premier appel de données).

## Décision

**Stocker le jeton dans `localStorage` et le valider par un appel `GET /me`** — à la
connexion **et** au démarrage de l'application.

- `GET /me` (OPP-103) est la **sonde d'authentification** : `200` avec l'identité
  (`{id, role, owned_count}`) si le jeton est valide, `401` sinon. C'est le point de
  vérité qui distingue un jeton valide d'un jeton simplement *présent*.
- Le jeton est persisté dans `localStorage` (`frontend/src/auth/authStorage.ts`) : simple,
  survit au rechargement, suffisant pour un dashboard interne.
- À tout changement de jeton, le `QueryClient` TanStack est **recréé**
  (`useMemo([token, logout])` dans `frontend/src/App.tsx`) : sans cela, un login ultérieur
  (même erroné) réafficherait les données mises en cache par la session précédente.
- La couche réseau lève un `ApiHttpError` **portant le `status`** (`frontend/src/api/client.ts`),
  pour que `QueryCache.onError` détecte un `401` et **purge le jeton** (déconnexion).

## Alternatives écartées

- **Session serveur robuste (cookies httpOnly / OAuth / refresh)** — c'est le périmètre
  d'**OPP-102**, laissé **conditionnel** : à instruire seulement si l'exposition ou les
  exigences de sécurité augmentent. Sur-dimensionné pour un MVP interne.
- **Valider uniquement la présence du jeton** — écarté : ouvre l'UI sur un jeton invalide
  (mauvaise expérience et faux sentiment de connexion). C'est la régression qu'`/me` corrige.
- **Jeton en mémoire seule (sessionStorage / state)** — écarté : imposerait une re-saisie
  à chaque rechargement, sans gain de sécurité réel dans ce contexte interne.

## Conséquences

- **Positives** : parcours de connexion simple et honnête (un jeton invalide est rejeté
  immédiatement) ; pas de couche de session à maintenir ; l'identité `/me` (dont le
  `role`) est disponible dès le démarrage pour piloter l'UI (utile pour les actions
  reviewer d'un futur Epic E10).
- **Négatives / risques** : `localStorage` est lisible par du JavaScript de la page — donc
  vulnérable en cas de faille XSS. Acceptable pour un dashboard interne à faible
  exposition ; **le jour où cette hypothèse tombe, ouvrir OPP-102** (cet ADR sera alors
  révisé). Pas d'expiration côté client au-delà de ce que l'API applique (l'échéance de
  jeton est gérée côté serveur, OPP-098/099).

## Références

- OPP-100 — Socle frontend + consultation d'un run
- OPP-103 — `GET /me`, sonde d'authentification + identité
- OPP-102 — Session d'authentification robuste (**différé**, conditionnel)
- OPP-098 / OPP-099 — Expiration des jetons (côté API)
- `frontend/src/auth/`, `frontend/src/api/client.ts`, `frontend/src/App.tsx`
