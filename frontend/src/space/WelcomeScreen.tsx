import { FlaskConical, FolderOpen } from "lucide-react";
import type { Space } from "./SpaceContext";
import { Logo } from "../components/Logo";

/**
 * Écran d'accueil (OPP-182) : à l'ouverture, choisir **« Mon espace »** (vraies données) ou
 * **« Démo »** (exemple isolé, jamais mélangé). Remplace l'ancien `LoginGate` (OPP-181) :
 * pas de login en local, juste le choix d'espace. Le clic pose l'en-tête `X-Opportune-Space`
 * et monte l'app sur la bonne base (cf. `SpaceProvider`).
 */
export function WelcomeScreen({ onChoose }: { onChoose: (space: Space) => void }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-surface px-4">
      <div className="text-center">
        {/* Signature au lieu du mot : le `<h1>` reste le titre de la page (texte en sr-only pour
            les lecteurs d'écran), le logo n'est que décoratif. */}
        <h1 className="flex justify-center">
          <span className="sr-only">Opportune</span>
          <Logo height={40} />
        </h1>
        <p className="mt-4 max-w-md text-sm text-ink-muted">
          Choisis ton espace de travail. La démo est un exemple isolé — tes vraies données n'y
          sont jamais mélangées.
        </p>
      </div>

      <div className="grid w-full max-w-2xl gap-4 sm:grid-cols-2">
        <button
          onClick={() => onChoose("mine")}
          className="group flex flex-col items-start gap-3 rounded-xl border border-border bg-surface-raised p-6 text-left shadow-sm transition-colors hover:border-brand/30 hover:bg-brand/5"
        >
          <FolderOpen className="h-7 w-7 text-brand" aria-hidden />
          <div>
            <div className="font-semibold text-ink">Mon espace</div>
            <p className="mt-1 text-sm text-ink-muted">
              Mes vraies recherches, offres et candidatures.
            </p>
          </div>
        </button>

        <button
          onClick={() => onChoose("demo")}
          className="group flex flex-col items-start gap-3 rounded-xl border border-border bg-surface-raised p-6 text-left shadow-sm transition-colors hover:border-warning/30 hover:bg-warning/5"
        >
          <FlaskConical className="h-7 w-7 text-warning" aria-hidden />
          <div>
            <div className="font-semibold text-ink">Démo</div>
            <p className="mt-1 text-sm text-ink-muted">
              Un exemple prêt à explorer, sans toucher à tes données.
            </p>
          </div>
        </button>
      </div>
    </div>
  );
}
