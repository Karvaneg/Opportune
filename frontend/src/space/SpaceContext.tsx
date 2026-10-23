import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { setApiSpace } from "../api/client";

/**
 * Espace de travail (OPP-182) : « Mon espace » (vraies données) ou « Démo » (exemple isolé).
 * Le back assemble deux bases SQLite distinctes et route chaque requête sur l'en-tête
 * `X-Opportune-Space` ; ici on mémorise le choix et on le pousse dans le client API.
 */
export type Space = "mine" | "demo";

// Persistance **par onglet** (`sessionStorage`) : recharger la page garde l'espace choisi, mais
// un nouvel onglet/une fermeture repart de l'accueil — un choix volontaire, pas collant à vie.
const STORAGE_KEY = "opportune.space";

function readStored(): Space | null {
  const value = sessionStorage.getItem(STORAGE_KEY);
  return value === "mine" || value === "demo" ? value : null;
}

interface SpaceValue {
  /** Espace choisi, ou `null` tant que l'accueil n'a pas tranché (→ écran d'accueil). */
  space: Space | null;
  /** Fixe l'espace (depuis l'accueil) : en-tête API posé, choix mémorisé pour l'onglet. */
  chooseSpace: (space: Space) => void;
  /** Revient à l'accueil (bascule d'espace) : en-tête retiré, choix oublié. */
  resetSpace: () => void;
}

const SpaceContext = createContext<SpaceValue | null>(null);

export function SpaceProvider({ children }: { children: ReactNode }) {
  // L'en-tête doit être posé **avant** le premier rendu des enfants (qui sondent `GET /me`) :
  // on l'initialise donc dès le calcul de l'état initial, pas dans un effet post-rendu.
  const [space, setSpace] = useState<Space | null>(() => {
    const stored = readStored();
    setApiSpace(stored);
    return stored;
  });

  const chooseSpace = useCallback((next: Space) => {
    setApiSpace(next);
    sessionStorage.setItem(STORAGE_KEY, next);
    setSpace(next);
  }, []);

  const resetSpace = useCallback(() => {
    setApiSpace(null);
    sessionStorage.removeItem(STORAGE_KEY);
    setSpace(null);
  }, []);

  const value = useMemo<SpaceValue>(
    () => ({ space, chooseSpace, resetSpace }),
    [space, chooseSpace, resetSpace],
  );

  return <SpaceContext.Provider value={value}>{children}</SpaceContext.Provider>;
}

export function useSpace(): SpaceValue {
  const ctx = useContext(SpaceContext);
  if (!ctx) throw new Error("useSpace doit être utilisé à l'intérieur d'un <SpaceProvider>");
  return ctx;
}
