# Frontend Opportune (V2, OPP-100) — isolé de la stack Python.
# Image de dev/test : installe les deps et sert Vite (ou lance Vitest).
FROM node:22-slim

WORKDIR /app

# Deps d'abord : maximise le cache de couches (réinstalle uniquement si les manifestes changent).
# `npm ci` sur le lockfile committé → installe des versions **déterministes** (pas de re-résolution
# des plages semver à chaque build), à la différence de `npm install`.
COPY package.json package-lock.json ./
RUN npm ci

# Code (monté en volume en dev via docker-compose ; copié ici pour build/test autonome).
COPY . .

EXPOSE 5173

# Par défaut : serveur de dev accessible hors conteneur. Tests : `docker run ... npm test`.
CMD ["npm", "run", "dev", "--", "--host"]
