import { FlaskConical, FolderOpen } from "lucide-react";
import type { Space } from "./SpaceContext";

/**
 * Écran d'accueil (OPP-182) : à l'ouverture, choisir **« Mon espace »** (vraies données) ou
 * **« Démo »** (exemple isolé, jamais mélangé). Remplace l'ancien `LoginGate` (OPP-181) :
 * pas de login en local, juste le choix d'espace. Le clic pose l'en-tête `X-Opportune-Space`
 * et monte l'app sur la bonne base (cf. `SpaceProvider`).
 */
export function WelcomeScreen({ onChoose }: { onChoose: (space: Space) => void }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-slate-50 px-4">
      <div className="text-center">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Opportune</h1>
        <p className="mt-2 max-w-md text-sm text-slate-500">
          Choisis ton espace de travail. La démo est un exemple isolé — tes vraies données n'y
          sont jamais mélangées.
        </p>
      </div>

      <div className="grid w-full max-w-2xl gap-4 sm:grid-cols-2">
        <button
          onClick={() => onChoose("mine")}
          className="group flex flex-col items-start gap-3 rounded-xl border border-slate-200 bg-white p-6 text-left shadow-sm transition-colors hover:border-indigo-300 hover:bg-indigo-50/40"
        >
          <FolderOpen className="h-7 w-7 text-indigo-600" aria-hidden />
          <div>
            <div className="font-semibold text-slate-900">Mon espace</div>
            <p className="mt-1 text-sm text-slate-500">
              Mes vraies recherches, offres et candidatures.
            </p>
          </div>
        </button>

        <button
          onClick={() => onChoose("demo")}
          className="group flex flex-col items-start gap-3 rounded-xl border border-slate-200 bg-white p-6 text-left shadow-sm transition-colors hover:border-amber-300 hover:bg-amber-50/40"
        >
          <FlaskConical className="h-7 w-7 text-amber-600" aria-hidden />
          <div>
            <div className="font-semibold text-slate-900">Démo</div>
            <p className="mt-1 text-sm text-slate-500">
              Un exemple prêt à explorer, sans toucher à tes données.
            </p>
          </div>
        </button>
      </div>
    </div>
  );
}
