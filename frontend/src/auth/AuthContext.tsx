import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiFetch } from "../api/client";
import type { Me } from "../api/types";

/**
 * État d'amorçage de l'app locale (OPP-181). Plus de jeton ni de login : Opportune est local
 * et mono-utilisateur. `checking` = on interroge `GET /me` au démarrage ; `ready` = l'API a
 * répondu, l'identité locale est connue ; `error` = l'API est injoignable (serveur non lancé),
 * on propose de réessayer plutôt qu'une barrière de login.
 */
type AuthStatus = "checking" | "ready" | "error";

interface AuthValue {
  status: AuthStatus;
  identity: Me | null;
  /** Relance `GET /me` — bouton « Réessayer » de l'écran « API injoignable ». */
  retry: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [identity, setIdentity] = useState<Me | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Au démarrage (et à chaque « Réessayer ») : sonde `GET /me`. Succès → identité locale et
  // app prête ; échec (API down) → état d'erreur, jamais de login. Aucun jeton n'est envoyé.
  useEffect(() => {
    let cancelled = false;
    setStatus("checking");
    apiFetch<Me>("/me")
      .then((me) => {
        if (cancelled) return;
        setIdentity(me);
        setStatus("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setIdentity(null);
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const value = useMemo(() => ({ status, identity, retry }), [status, identity, retry]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé à l'intérieur d'un <AuthProvider>");
  return ctx;
}
