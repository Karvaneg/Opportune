# ADR 0003 — Local-first, mono-utilisateur : plus d'authentification ni de jeton

- **Statut** : Accepté — **en vigueur**
- **Date** : 2026-10-23
- **Contexte ticket** : OPP-181 (Epic E11 — Refonte recherches multiples)
- **Décideurs** : équipe Opportune
- **Remplace** : [`ADR 0002`](0002-auth-frontend-localstorage-me.md)

## Contexte

L'ADR 0002 avait retenu un jeton porteur stocké en `localStorage` et validé par `GET /me`,
pour un « dashboard interne à faible exposition ». La direction du produit a depuis été
clarifiée : **Opportune reste local sur la machine de l'utilisateur** — pas d'hébergement,
une seule personne, un serveur qui n'écoute que sur `localhost`. Dans ce cadre, le
login/jeton n'apporte **aucune sécurité réelle** (qui atteint `localhost` est déjà sur la
machine) et n'ajoute que de la friction : saisie d'un jeton, écran de login, gestion de
l'expiration côté client.

## Décision

**Supprimer toute authentification côté frontend et tout jeton côté API.**

- L'API démarre **sans jeton** et n'écoute que sur `localhost` (mono-utilisateur).
- `GET /me` reste la **sonde d'amorçage** : au démarrage, le frontend l'appelle pour
  identifier l'unique utilisateur local. Succès → l'app est prête ; échec (serveur non
  lancé) → écran « API injoignable » avec un bouton « Réessayer », **jamais** un écran de
  login.
- Plus de jeton porteur, plus de `localStorage` d'auth, plus de flux de connexion :
  `frontend/src/auth/authStorage.ts` est supprimé ; `AuthContext` ne gère plus qu'un état
  d'amorçage (`checking` / `ready` / `error`).

## Alternatives écartées

- **Conserver le jeton en `localStorage` (ADR 0002)** — écarté : sécurité illusoire en
  local, friction inutile pour un unique utilisateur sur sa propre machine.
- **Session serveur robuste (cookies httpOnly / OAuth)** — toujours hors périmètre (c'était
  déjà l'OPP-102 différé) ; ne se justifierait qu'avec une exposition réseau, contraire à la
  direction local-first.

## Conséquences

- **Positives** : installation et usage plus simples (aucun secret à saisir pour démarrer) ;
  moins de code (plus de couche d'auth à maintenir) ; cohérent avec la priorité « simplicité
  d'installation pour les tiers ».
- **Négatives / risques** : l'API **ne doit jamais** être exposée au-delà de `localhost` en
  l'état (aucun contrôle d'accès). Le jour où une exposition réseau ou un multi-utilisateur
  redeviendrait nécessaire, il faudrait **rouvrir l'OPP-102** (session robuste) et réviser cet
  ADR. Le rôle (`reviewer`) renvoyé par `GET /me` subsiste pour piloter l'UI des actions
  sensibles, mais n'est plus un contrôle d'authentification.

## Références

- OPP-181 — Retirer le token (auth locale sans jeton)
- [`ADR 0002`](0002-auth-frontend-localstorage-me.md) — décision d'origine (remplacée)
- `frontend/src/auth/AuthContext.tsx` — état d'amorçage local
- `docs/vision.md` — direction local-first
