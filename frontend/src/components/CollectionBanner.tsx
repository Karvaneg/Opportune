import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useActiveCollectJob, useCancelCollect } from "../api/offers";
import { CollectCounts } from "./CollectCounts";

/**
 * Indicateur **global** de collecte en cours (OPP-208). Monté haut dans l'app (sous le header,
 * tous écrans), il interroge le job **actif** (`GET /collect`, sans `job_id`) : il survit donc
 * au changement de page, là où le suivi local de `CollectOffers` disparaît. Ne s'affiche que
 * pendant une passe `running` ; le bilan final reste du ressort de la page Offres. Les compteurs
 * montent (pas de barre %, le total n'est pas connu d'avance).
 *
 * Porte aussi le bouton **Arrêter** (OPP-209) : l'arrêt est coopératif (effectif au prochain
 * point de contrôle du runner), d'où l'état intermédiaire « Arrêt en cours… » tant que
 * `cancel_requested` est vrai.
 */
export function CollectionBanner() {
  const { data } = useActiveCollectJob();
  const cancel = useCancelCollect();
  const job = data?.job;
  if (!job || job.status !== "running") return null;

  const stopping = job.cancel_requested || cancel.isPending;
  return (
    <div className="border-b border-brand/30 bg-brand/10">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm sm:px-6">
        <span className="flex items-center gap-2 text-brand">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Collecte d'offres en cours… <CollectCounts progress={job.progress} />
        </span>
        <div className="flex items-center gap-3">
          <Link to="/offres" className="font-medium text-brand underline hover:text-brand-strong">
            Voir
          </Link>
          <button
            type="button"
            onClick={() => cancel.mutate(job.job_id)}
            disabled={stopping}
            className="rounded-md px-2 py-1 font-medium text-brand transition-colors hover:bg-brand/15 disabled:opacity-50"
          >
            {stopping ? "Arrêt en cours…" : "Arrêter"}
          </button>
        </div>
      </div>
    </div>
  );
}
