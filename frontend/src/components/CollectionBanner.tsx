import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useActiveCollectJob } from "../api/offers";

/**
 * Indicateur **global** de collecte en cours (OPP-208). Monté haut dans l'app (sous le header,
 * tous écrans), il interroge le job **actif** (`GET /collect`, sans `job_id`) : il survit donc
 * au changement de page, là où le suivi local de `CollectOffers` disparaît. Ne s'affiche que
 * pendant une passe `running` ; le bilan final reste du ressort de la page Offres. Les compteurs
 * montent (pas de barre %, le total n'est pas connu d'avance).
 */
export function CollectionBanner() {
  const { data } = useActiveCollectJob();
  const job = data?.job;
  if (!job || job.status !== "running") return null;

  const { collected, stored, duplicates } = job.progress;
  return (
    <div className="border-b border-brand/30 bg-brand/10">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm sm:px-6">
        <span className="flex items-center gap-2 text-brand">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Collecte d'offres en cours… {collected} collectée{collected > 1 ? "s" : ""} ·{" "}
          {stored} nouvelle{stored > 1 ? "s" : ""} · {duplicates} doublon
          {duplicates > 1 ? "s" : ""}
        </span>
        <Link to="/offres" className="font-medium text-brand underline hover:text-brand-strong">
          Voir
        </Link>
      </div>
    </div>
  );
}
