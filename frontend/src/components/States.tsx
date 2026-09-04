import { ApiHttpError } from "../api/client";

/** Indicateur de chargement neutre. */
export function Loading({ label = "Chargement…" }: { label?: string }) {
  return (
    <p className="rounded-lg border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
      {label}
    </p>
  );
}

/**
 * Affiche une erreur. Les messages sont déjà neutralisés par `apiFetch`
 * (404 anti-énumération, etc.) ; on retombe sur un texte générique sinon.
 */
export function ErrorNotice({ error }: { error: unknown }) {
  const message =
    error instanceof ApiHttpError || error instanceof Error
      ? error.message
      : "Une erreur est survenue.";
  return (
    <p className="rounded-lg border border-red-200 bg-red-50 p-6 text-center text-sm text-red-700">
      {message}
    </p>
  );
}
