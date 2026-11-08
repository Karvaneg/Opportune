import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { parsePage } from "../lib/parsePage";
import { useSearchParamsUpdate } from "./useSearchParamsUpdate";

/**
 * Numéro de page d'une liste paginée, porté par l'adresse (`?page=`, OPP-239, généralisé en
 * OPP-240) : il survit à l'aller-retour vers une fiche. La page 1 n'est jamais écrite dans
 * l'adresse ; les autres paramètres (filtres) et le `state` de navigation sont conservés. À
 * compléter par `useClampPage` une fois la réponse du serveur connue.
 */
export function usePageParam(): [number, (next: number) => void] {
  const [searchParams] = useSearchParams();
  const update = useSearchParamsUpdate();
  const page = parsePage(searchParams.get("page"));

  const setPage = (next: number) =>
    update((params) => {
      if (next <= 1) params.delete("page");
      else params.set("page", String(next));
    });

  return [page, setPage];
}

/**
 * Ramène une page au-delà de la dernière (favori `?page=50`, liste qui a diminué) sur la
 * dernière. On attend une réponse **à jour** du serveur : ni les données de la page précédente
 * affichées pendant un chargement (`isPlaceholderData`), ni une réponse en cache en cours de
 * rafraîchissement (`isFetching`), dont le nombre de pages peut être périmé.
 */
export function useClampPage(
  page: number,
  setPage: (next: number) => void,
  query: { data?: { total_pages: number }; isPlaceholderData: boolean; isFetching: boolean },
): void {
  const { data, isPlaceholderData, isFetching } = query;
  const lastPage =
    data && !isPlaceholderData && !isFetching ? Math.max(data.total_pages, 1) : null;
  useEffect(() => {
    // `setPage` change à chaque changement d'adresse : on ne le met pas dans les dépendances,
    // l'effet ne doit réagir qu'à la page demandée et à la dernière page connue. La version
    // capturée est celle du dernier rendu, donc à jour quand l'effet s'exécute.
    if (lastPage !== null && page > lastPage) setPage(lastPage);
  }, [lastPage, page]);
}
