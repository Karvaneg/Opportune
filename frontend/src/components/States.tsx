import { ApiHttpError } from "../api/client";

/** Indicateur de chargement neutre. */
export function Loading({ label = "Chargement…" }: { label?: string }) {
  return (
    <p className="rounded-lg border border-border bg-surface-raised p-6 text-center text-sm text-ink-muted">
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
    <p className="rounded-lg border border-danger/30 bg-danger/10 p-6 text-center text-sm text-danger">
      {message}
    </p>
  );
}
