import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiHttpError } from "./client";

/**
 * QueryClient qui réagit à l'expiration de session (OPP-102). Un **401 sur n'importe quelle
 * requête** — lecture (`QueryCache`) comme écriture (`MutationCache`) — déclenche
 * `onAuthExpired`, remontant à la couche d'auth pour purger le jeton et revenir à la
 * barrière de login.
 *
 * Le `MutationCache` est la pièce manquante d'avant OPP-102 : seules les lectures
 * purgeaient le 401 ; un jeton expiré pendant une **action** (valider une reco, générer
 * une lettre, ajouter une offre) laissait l'UI « authentifiée » face à des erreurs, sans
 * jamais rebasculer au login.
 */
export function createAuthAwareQueryClient(onAuthExpired: () => void): QueryClient {
  const handle = (error: unknown) => {
    if (error instanceof ApiHttpError && error.status === 401) onAuthExpired();
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError: handle }),
    mutationCache: new MutationCache({ onError: handle }),
    defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
  });
}
