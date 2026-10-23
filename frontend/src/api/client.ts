import type { ApiErrorBody } from "./types";

// Préfixe des appels API : réécrit par le proxy Vite vers l'API Python (cf. vite.config.ts).
// Isole les appels réseau des routes client React Router (`/runs/:runId`).
const API_BASE = "/api";

/**
 * Erreur HTTP de l'API portant le `status` (et le corps si disponible).
 *
 * On conserve le `status` — au lieu d'un simple `Error` — pour que l'appelant distingue les
 * cas (400 saisie, 403 rôle, 404 neutre, 409 conflit) et réagisse en conséquence.
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
 * Lecture de l'API (GET). Renvoie le JSON typé `T` en cas de succès, lève un `ApiHttpError`
 * (status préservé) sinon. Local-first (OPP-181) : aucun jeton, pas d'en-tête `Authorization`.
 */
export async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      Accept: "application/json",
    },
  });

  return parseOrThrow<T>(response);
}

/**
 * Écriture de l'API (POST + corps JSON). Même contrat d'erreur qu'`apiFetch`
 * (`ApiHttpError` porteur du `status`) — l'appelant distingue 400/403/404/409 (cf. OPP-105).
 */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body ?? {}),
  });

  return parseOrThrow<T>(response);
}

/**
 * Mise à jour (PUT + corps JSON). Même contrat d'erreur qu'`apiPost` : utilisé pour l'édition
 * d'une lettre (`PUT /recommendations/{id}/letter`, OPP-147).
 */
export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body ?? {}),
  });

  return parseOrThrow<T>(response);
}

/**
 * Suppression (DELETE). Même contrat d'erreur qu'`apiFetch` (`ApiHttpError` porteur du
 * `status`) — l'appelant distingue 403/404.
 */
export async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: {
      Accept: "application/json",
    },
  });

  return parseOrThrow<T>(response);
}
