import { QueryClient } from "@tanstack/react-query";

/**
 * QueryClient de l'app locale (OPP-181). Plus de gestion d'expiration de session : local-first,
 * mono-utilisateur, sans jeton — un 401 ne peut plus survenir. On garde les réglages de cache
 * (pas de retry automatique, fraîcheur courte) ; l'app le crée une fois au montage.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
  });
}
