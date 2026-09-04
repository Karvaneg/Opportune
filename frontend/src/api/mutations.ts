import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";

/**
 * Socle des écritures (OPP-105). Enveloppe `useMutation` en injectant le jeton courant
 * (via `useAuth`) et en invalidant, après succès, les clés de cache retournées par
 * `invalidateKeys` — mécanisme générique consommé par la validation (OPP-108) et la
 * confirmation de candidature (OPP-110).
 *
 * Les erreurs remontent telles quelles (des `ApiHttpError` porteurs du `status`, cf.
 * `apiPost`) : l'appelant distingue 400/403/404/409, et `QueryCache.onError` purge le 401.
 */
interface UseApiMutationOptions<TData, TVariables> {
  /** Écriture réseau ; reçoit le jeton déjà résolu (jamais à passer par l'appelant). */
  mutationFn: (variables: TVariables, token: string) => Promise<TData>;
  /** Clés (ou préfixes) à invalider après succès — ex. `runKeys.run(runId)`. */
  invalidateKeys?: (variables: TVariables, data: TData) => readonly QueryKey[];
  /** Effet additionnel après succès (navigation, toast…), après l'invalidation. */
  onSuccess?: (data: TData, variables: TVariables) => void;
}

export function useApiMutation<TData, TVariables = void>({
  mutationFn,
  invalidateKeys,
  onSuccess,
}: UseApiMutationOptions<TData, TVariables>) {
  const { token } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<TData, Error, TVariables>({
    mutationFn: (variables) => {
      // Garde le contrat robuste : plutôt qu'un `token!` qui laisserait filer un
      // `Bearer null` (→ 401 opaque), on échoue clairement si aucun jeton n'est actif.
      if (!token) throw new Error("useApiMutation : aucun jeton actif");
      return mutationFn(variables, token);
    },
    onSuccess: (data, variables) => {
      for (const queryKey of invalidateKeys?.(variables, data) ?? []) {
        queryClient.invalidateQueries({ queryKey });
      }
      onSuccess?.(data, variables);
    },
  });
}
