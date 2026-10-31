import type { LlmNotReadyReason } from "../api/system";
import { Hint } from "./States";

/**
 * Explique pourquoi une action est désactivée tant que le LLM local n'est pas prêt (OPP-195) :
 * son modèle s'installe, ou le moteur Ollama est injoignable. L'installation et le « Réessayer »
 * vivent dans le bandeau global (`LlmBanner`), d'où le renvoi vers « le bandeau en haut » plutôt
 * qu'un lien : il n'y a pas de page dédiée.
 */
export function LlmRequiredNotice({ reason }: { reason: LlmNotReadyReason }) {
  return (
    <Hint>
      {reason === "unreachable"
        ? "L'assistant local (Ollama) est injoignable : cette action le requiert. Démarre-le, puis réessaie depuis le bandeau en haut."
        : "L'assistant local se prépare (installation du modèle, voir le bandeau en haut) : cette action sera disponible dès qu'il est prêt."}
    </Hint>
  );
}
