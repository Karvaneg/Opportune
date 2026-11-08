import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiFetch } from "./client";
import type { Me } from "./types";

/**
 * État de l'API locale au démarrage (OPP-181, renommé en OPP-241). Plus de jeton ni de login ni de
 * rôle : Opportune est local et mono-utilisateur. `checking` = on interroge `GET /me` ; `ready` =
 * l'API a répondu ; `error` = l'API est injoignable (serveur non lancé), on propose de réessayer.
 */
type ApiStatus = "checking" | "ready" | "error";

interface ApiStatusValue {
  status: ApiStatus;
  /** Relance `GET /me` : bouton « Réessayer » de l'écran « API injoignable ». */
  retry: () => void;
}

const ApiStatusContext = createContext<ApiStatusValue | null>(null);

export function ApiStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<ApiStatus>("checking");
  const [attempt, setAttempt] = useState(0);

  // Au démarrage (et à chaque « Réessayer ») : sonde `GET /me`. Succès → app prête ; échec (API
  // arrêtée) → état d'erreur. Aucun jeton n'est envoyé.
  useEffect(() => {
    let cancelled = false;
    setStatus("checking");
    apiFetch<Me>("/me")
      .then(() => {
        if (!cancelled) setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const value = useMemo(() => ({ status, retry }), [status, retry]);

  return <ApiStatusContext.Provider value={value}>{children}</ApiStatusContext.Provider>;
}

export function useApiStatus(): ApiStatusValue {
  const ctx = useContext(ApiStatusContext);
  if (!ctx) {
    throw new Error("useApiStatus doit être utilisé à l'intérieur d'un <ApiStatusProvider>");
  }
  return ctx;
}
