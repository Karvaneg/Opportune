import type { LlmNotReadyReason } from "../api/system";

/**
 * Explique pourquoi une action est désactivée tant que le LLM local n'est pas prêt (OPP-195) :
 * son modèle s'installe, ou le moteur Ollama est injoignable. L'installation et le « Réessayer »
 * vivent dans le bandeau global (`LlmBanner`), d'où le renvoi vers « le bandeau en haut » plutôt
 * qu'un lien : il n'y a pas de page dédiée.
 */
export function LlmRequiredNotice({ reason }: { reason: LlmNotReadyReason }) {
  return (
    <p className="rounded-md border border-dashed border-border bg-surface p-3 text-sm text-ink-muted">
      {reason === "unreachable"
        ? "L'assistant local (Ollama) est injoignable : cette action le requiert. Démarre-le, puis réessaie depuis le bandeau en haut."
        : "L'assistant local se prépare (installation du modèle, voir le bandeau en haut) : cette action sera disponible dès qu'il est prêt."}
    </p>
  );
}
