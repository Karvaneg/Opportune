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

/**
 * Appel authentifié à l'API. Renvoie le JSON typé `T` en cas de succès,
 * lève un `ApiHttpError` (status préservé) sinon.
 */
export async function apiFetch<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiHttpError(response.status, messageFor(response.status, body), body);
  }

  return response.json() as Promise<T>;
}
