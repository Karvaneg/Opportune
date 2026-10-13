import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiHttpError, apiFetch } from "../api/client";
import type { Me } from "../api/types";
import { purgeLegacyLocalToken, sessionAuthStorage, type AuthStorage } from "./authStorage";

/** `checking` = jeton en cours de vérification (`GET /me`) ; on ne montre pas la coquille. */
type AuthStatus = "checking" | "anonymous" | "authenticated";

/** Message affiché à la barrière quand la session a expiré **en cours d'usage** (OPP-102). */
export const SESSION_EXPIRED_MESSAGE = "Session expirée — veuillez vous reconnecter.";

interface AuthValue {
  status: AuthStatus;
  token: string | null;
  identity: Me | null;
  error: string | null;
  /** Vérifie le jeton via `GET /me` ; n'authentifie que s'il est **accepté** (≠ 401). */
  login: (token: string) => Promise<void>;
  /** Déconnexion volontaire (bouton) : retour anonyme, sans message d'erreur. */
  logout: () => void;
  /**
   * Fin de session **subie** : un 401 survenu alors qu'on était authentifié (jeton
   * expiré/révoqué). Même effet que `logout`, mais affiche `SESSION_EXPIRED_MESSAGE` pour
   * expliquer le retour à la barrière plutôt que de larguer l'utilisateur sans contexte.
   */
  expireSession: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({
  children,
  storage = sessionAuthStorage,
}: {
  children: ReactNode;
  storage?: AuthStorage;
}) {
  const [token, setToken] = useState<string | null>(() => storage.get());
  const [identity, setIdentity] = useState<Me | null>(null);
  const [status, setStatus] = useState<AuthStatus>(() =>
    storage.get() ? "checking" : "anonymous",
  );
  const [error, setError] = useState<string | null>(null);

  // Remise à l'état anonyme, partagée par la déconnexion volontaire et l'expiration subie.
  // Le `reason` (null = aucun) distingue les deux côté barrière de login.
  const reset = useCallback(
    (reason: string | null) => {
      storage.clear();
      setToken(null);
      setIdentity(null);
      setStatus("anonymous");
      setError(reason);
    },
    [storage],
  );

  // Migration OPP-102 : purge une fois l'éventuel jeton hérité de `localStorage` (défaut
  // d'avant la bascule vers `sessionStorage`), pour ne pas laisser un secret y traîner.
  useEffect(() => {
    purgeLegacyLocalToken();
  }, []);

  // Au démarrage : un jeton stocké est **revérifié** (il a pu expirer). Tant qu'on ne l'a
  // pas confirmé via /me, on reste en `checking` — jamais de coquille sur un jeton périmé.
  useEffect(() => {
    const stored = storage.get();
    if (!stored) return;
    let cancelled = false;
    apiFetch<Me>("/me", stored)
      .then((me) => {
        if (cancelled) return;
        setIdentity(me);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        // Le jeton de cette session d'onglet n'est plus accepté → même traitement qu'une
        // expiration en cours d'usage : retour anonyme AVEC message, pas un largage muet.
        reset(SESSION_EXPIRED_MESSAGE);
      });
    return () => {
      cancelled = true;
    };
  }, [storage, reset]);

  const login = useCallback(
    async (next: string) => {
      const trimmed = next.trim();
      if (!trimmed) return;
      setError(null);
      setStatus("checking");
      try {
        const me = await apiFetch<Me>("/me", trimmed);
        storage.set(trimmed);
        setToken(trimmed);
        setIdentity(me);
        setStatus("authenticated");
      } catch (e) {
        setToken(null);
        setIdentity(null);
        setStatus("anonymous");
        setError(
          e instanceof ApiHttpError && e.status === 401
            ? "Jeton invalide."
            : "Connexion impossible — API injoignable ?",
        );
      }
    },
    [storage],
  );

  const logout = useCallback(() => reset(null), [reset]);
  const expireSession = useCallback(() => reset(SESSION_EXPIRED_MESSAGE), [reset]);

  const value = useMemo(
    () => ({ status, token, identity, error, login, logout, expireSession }),
    [status, token, identity, error, login, logout, expireSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé à l'intérieur d'un <AuthProvider>");
  return ctx;
}
