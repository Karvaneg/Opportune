import { apiPost } from "./client";

/**
 * Commandes de l'espace démo (OPP-182). Portées par le routeur back : elles agissent toujours
 * sur la base démo isolée, jamais sur les vraies données. `reset` vide la démo (bac à sable
 * repartant de zéro), `restore` restaure la vitrine d'exemple canonique.
 */
export function resetDemo(): Promise<{ status: string }> {
  return apiPost<{ status: string }>("/demo/reset", {});
}

export function restoreDemo(): Promise<{ status: string }> {
  return apiPost<{ status: string }>("/demo/restore", {});
}
