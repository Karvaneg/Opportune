import { Link } from "react-router-dom";
import { useProfile } from "../api/profile";

/** Accorde « compétence(s) », « expérience(s) » au pluriel selon le compte. */
function plural(count: number, word: string): string {
  return `${count} ${word}${count > 1 ? "s" : ""}`;
}

/**
 * Carte résumé du profil sur le cockpit : le profil détaillé (CV, compétences, parcours) vit
 * désormais sur sa page dédiée (`/profil`). Ici on ne donne qu'un aperçu — nom, contrat, volume
 * de compétences et d'expériences — avec un accès direct. Un profil non renseigné (404) invite à
 * le compléter plutôt que de signaler une erreur : c'est l'état attendu d'un nouveau candidat.
 */
export function ProfileSummaryCard({ candidateId }: { candidateId: string }) {
  const { data, isPending, isError } = useProfile(candidateId);
  if (candidateId === "") return null;

  const missing = isError || !data;
  const skillCount = data?.skills.length ?? 0;
  const expCount = data?.experiences?.length ?? 0;

  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white p-4">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Profil</h3>
        {isPending ? (
          <p className="mt-1 text-sm text-slate-400">Chargement…</p>
        ) : missing ? (
          <p className="mt-1 text-sm text-slate-600">Profil non renseigné — importe ton CV.</p>
        ) : (
          <p className="mt-1 truncate text-sm text-slate-600">
            {data.name}
            {data.contract_type ? ` · ${data.contract_type}` : ""} · {plural(skillCount, "compétence")}{" "}
            · {plural(expCount, "expérience")}
          </p>
        )}
      </div>
      <Link
        to="/profil"
        className="shrink-0 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        {missing && !isPending ? "Compléter" : "Voir"}
      </Link>
    </div>
  );
}
