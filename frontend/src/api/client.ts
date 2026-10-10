import type { ApiErrorBody } from "./types";

// Préfixe des appels API : réécrit par le proxy Vite vers l'API Python (cf. vite.config.ts).
// Isole les appels réseau des routes client React Router (`/runs/:runId`).
const API_BASE = "/api";

/**
 * Erreur HTTP de l'API portant le `status` (et le corps si disponible).
 *
 * On conserve le `status` — au lieu d'un simple `Error` — pour que la couche d'auth
 * puisse réagir spécifiquement au 401 (purge du jeton), cf. OPP-100.
 */
export class ApiHttpError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody | null;

  constructor(status: number, message: string, body: ApiErrorBody | null) {
    super(message);
    this.name = "ApiHttpError";
    this.status = status;
    this.body = body;
  }
}

/** Message affichable dérivé du status. 404 volontairement NEUTRE (anti-énumération). */
function messageFor(status: number, body: ApiErrorBody | null): string {
  switch (status) {
    case 401:
      return "Session expirée ou jeton invalide.";
    case 403:
      return "Accès refusé : rôle insuffisant.";
    case 404:
      // « Inexistant » et « hors périmètre » sont indistinguables côté API : message neutre.
      return "Run introuvable ou inaccessible.";
    default:
      return body?.error ?? "Une erreur est survenue.";
  }
}

/** Interprète la réponse : JSON typé `T` si 2xx, `ApiHttpError` (status préservé) sinon. */
async function parseOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiHttpError(response.status, messageFor(response.status, body), body);
  }

  return response.json() as Promise<T>;
}

/**
 * Lecture authentifiée de l'API (GET). Renvoie le JSON typé `T` en cas de succès,
 * lève un `ApiHttpError` (status préservé) sinon.
 */
export async function apiFetch<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  });

  return parseOrThrow<T>(response);
}

/**
 * Écriture authentifiée de l'API (POST + corps JSON). Même contrat d'erreur qu'`apiFetch`
 * (`ApiHttpError` porteur du `status`) — indispensable pour que la couche d'auth réagisse
 * au 401 et que l'appelant distingue 400/403/404/409 (cf. OPP-105).
 */
export async function apiPost<T>(path: string, token: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body ?? {}),
  });

  return parseOrThrow<T>(response);
}

/**
 * Mise à jour authentifiée (PUT + corps JSON). Même contrat d'erreur qu'`apiPost` : utilisé
 * pour l'édition d'une lettre (`PUT /recommendations/{id}/letter`, OPP-147).
 */
export async function apiPut<T>(path: string, token: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body ?? {}),
  });

  return parseOrThrow<T>(response);
}

/**
 * Suppression authentifiée (DELETE). Même contrat d'erreur qu'`apiFetch` (`ApiHttpError`
 * porteur du `status`) — l'appelant distingue 403/404 et `QueryCache.onError` purge le 401.
 */
export async function apiDelete<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  });

  return parseOrThrow<T>(response);
}
