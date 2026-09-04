// Abstraction de stockage du jeton — remplaçable par une vraie session (OPP-102)
// sans toucher au reste du front. Le MVP s'appuie sur localStorage.

export interface AuthStorage {
  get(): string | null;
  set(token: string): void;
  clear(): void;
}

const TOKEN_KEY = "opportune.auth.token";

/** Implémentation localStorage, tolérante aux environnements sans stockage (SSR, privé). */
export const localAuthStorage: AuthStorage = {
  get() {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* stockage indisponible : on reste en mémoire via le state React */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* rien à faire */
    }
  },
};
