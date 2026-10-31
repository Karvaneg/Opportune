import type { ReactNode } from "react";
import { ApiHttpError } from "../api/client";

/**
 * Encart d'information **neutre** (bord pointillé) : messages d'aide ou de prérequis non
 * bloquants — LLM à installer, clés Adzuna manquantes, flux RSS à renseigner, action réservée au
 * reviewer. Centralise le style partagé par ces encarts, pour qu'un ajustement de tokens (bord,
 * fond, espacement) se fasse à un seul endroit plutôt que recopié dans chaque composant.
 */
export function Hint({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-dashed border-border bg-surface p-3 text-sm text-ink-muted">
      {children}
    </p>
  );
}

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
