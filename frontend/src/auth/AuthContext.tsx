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
import { localAuthStorage, type AuthStorage } from "./authStorage";

/** `checking` = jeton en cours de vérification (`GET /me`) ; on ne montre pas la coquille. */
type AuthStatus = "checking" | "anonymous" | "authenticated";

interface AuthValue {
  status: AuthStatus;
  token: string | null;
  identity: Me | null;
  error: string | null;
  /** Vérifie le jeton via `GET /me` ; n'authentifie que s'il est **accepté** (≠ 401). */
  login: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({
  children,
  storage = localAuthStorage,
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
        storage.clear();
        setToken(null);
        setStatus("anonymous");
      });
    return () => {
      cancelled = true;
    };
  }, [storage]);

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

  const logout = useCallback(() => {
    storage.clear();
    setToken(null);
    setIdentity(null);
    setStatus("anonymous");
    setError(null);
  }, [storage]);

  const value = useMemo(
    () => ({ status, token, identity, error, login, logout }),
    [status, token, identity, error, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé à l'intérieur d'un <AuthProvider>");
  return ctx;
}
