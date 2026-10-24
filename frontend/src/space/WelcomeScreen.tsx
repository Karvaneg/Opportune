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
        {/* Lockup signature + baseline : le bloc est centré dans la page, mais la baseline s'aligne
            sous le DÉBUT du mot (bord gauche), comme la couverture de la charte — pas centrée sous
            la signature. `inline-flex` prend la largeur du logo ; `items-start` cale la baseline à
            gauche. `ml-0.5` reprend le léger retrait de la charte (margin-left 4px, ~proportionnel).
            Le `<h1>` reste le titre de page (« Opportune » en sr-only), le logo étant décoratif. */}
        <div className="inline-flex flex-col items-start">
          <h1 className="flex">
            <span className="sr-only">Opportune</span>
            <Logo height={48} />
          </h1>
          <p className="-mt-1 ml-0 text-base text-ink-muted">Saisir l'occasion au vol.</p>
        </div>
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
