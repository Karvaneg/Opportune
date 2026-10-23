import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";

/**
 * Socle des écritures (OPP-105). Enveloppe `useMutation` en invalidant, après succès, les clés
 * de cache retournées par `invalidateKeys` — mécanisme générique consommé par la validation
 * (OPP-108) et la confirmation de candidature (OPP-110). Local-first (OPP-181) : plus de jeton
 * à injecter, l'écriture appelle directement l'API.
 *
 * Les erreurs remontent telles quelles (des `ApiHttpError` porteurs du `status`, cf.
 * `apiPost`) : l'appelant distingue 400/403/404/409.
 */
interface UseApiMutationOptions<TData, TVariables> {
  /** Écriture réseau. */
  mutationFn: (variables: TVariables) => Promise<TData>;
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
  const queryClient = useQueryClient();

  return useMutation<TData, Error, TVariables>({
    // Enveloppe pour ne passer QUE les variables : React Query appellerait sinon la fonction
    // avec un 2ᵉ argument (contexte interne), que les écritures n'attendent pas.
    mutationFn: (variables) => mutationFn(variables),
    onSuccess: (data, variables) => {
      for (const queryKey of invalidateKeys?.(variables, data) ?? []) {
        queryClient.invalidateQueries({ queryKey });
      }
      onSuccess?.(data, variables);
    },
  });
}
