// Abstraction de stockage du jeton — remplaçable sans toucher au reste du front (OPP-100).
//
// OPP-102 bascule le défaut de `localStorage` vers `sessionStorage` : le jeton ne survit
// plus à la fermeture de l'onglet (session liée à l'onglet, pas un secret qui traîne
// indéfiniment dans un store partagé). Combiné à l'auto-logout sur 401 (cf. `App.tsx`),
// on tient une vraie notion de session côté client sans refonte du schéma back (jeton
// Bearer statique, à expiration optionnelle via `OPPORTUNE_API_TOKEN_TTL`).

export interface AuthStorage {
  get(): string | null;
  set(token: string): void;
  clear(): void;
}

const TOKEN_KEY = "opportune.auth.token";

/**
 * Fabrique une `AuthStorage` adossée à un `Storage` web (`localStorage`/`sessionStorage`),
 * tolérante aux environnements sans stockage (SSR, navigation privée) : l'accès est
 * paresseux (`area()`) et toute erreur retombe silencieusement sur le state React en mémoire.
 */
function createWebAuthStorage(area: () => Storage): AuthStorage {
  return {
    get() {
      try {
        return area().getItem(TOKEN_KEY);
      } catch {
        return null;
      }
    },
    set(token: string) {
      try {
        area().setItem(TOKEN_KEY, token);
      } catch {
        /* stockage indisponible : on reste en mémoire via le state React */
      }
    },
    clear() {
      try {
        area().removeItem(TOKEN_KEY);
      } catch {
        /* rien à faire */
      }
    },
  };
}

/** Stockage de session (défaut OPP-102) : vidé à la fermeture de l'onglet. */
export const sessionAuthStorage: AuthStorage = createWebAuthStorage(() => sessionStorage);

/**
 * Nettoyage de migration OPP-102 : avant cette bascule le jeton était écrit dans
 * `localStorage`. On l'y purge une fois (idempotent, tolérant aux stockages indisponibles)
 * pour ne pas laisser un secret traîner indéfiniment dans un store partagé une fois la
 * session passée à `sessionStorage`. À appeler une fois au démarrage (cf. `AuthProvider`).
 */
export function purgeLegacyLocalToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* stockage indisponible : rien à purger */
  }
}
