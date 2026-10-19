import { useNavigate } from "react-router-dom";
import { useCandidateStats } from "../api/stats";
import type { FunnelStage } from "../api/funnel";
import { useTargetCandidate } from "../auth/useTargetCandidate";
import { AddOffer } from "../components/AddOffer";
import { LaunchRun } from "../components/LaunchRun";
import { ErrorNotice, Loading } from "../components/States";

/**
 * Cockpit — page d'accueil de synthèse (OPP-164). Répond à « qu'est-ce que je dois traiter
 * maintenant ? » : trois compteurs d'avancement (à étudier / à postuler / postulé) depuis
 * `GET /candidates/{id}/stats` (OPP-163), plus les raccourcis d'action (lancer une analyse,
 * ajouter une offre). Les deux premières cartes sont cliquables et ouvrent Offres pré-filtré
 * par action recommandée. Remplace l'ancien accueil « Runs », désormais sous « Historique ».
 */
export function CockpitPage() {
  // Candidat ciblé pour les compteurs. Défaut : le 1er du périmètre (même logique qu'OffersPage).
  const { candidates, target, setCandidate } = useTargetCandidate();
  const { data, isPending, isError, error } = useCandidateStats(target);

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold text-slate-900">Accueil</h2>
        {candidates.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-slate-500">
            Candidat
            <select
              aria-label="Candidat pour la synthèse"
              value={target}
              onChange={(e) => setCandidate(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            >
              {candidates.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {target === "" ? (
        <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
          Aucun candidat dans votre périmètre.
        </p>
      ) : (
        <>
          {isPending && <Loading label="Chargement de la synthèse…" />}
          {isError && <ErrorNotice error={error} />}
          {data && <StatCards candidateId={target} stats={data} />}
        </>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Nouvelle analyse
          </h3>
          <LaunchRun />
        </div>
        <AddOffer />
      </div>
    </section>
  );
}

/** Les trois compteurs d'avancement + le total du pool. */
function StatCards({
  candidateId,
  stats,
}: {
  candidateId: string;
  stats: { a_etudier: number; a_postuler: number; postule: number; offres_total: number };
}) {
  return (
    <div className="space-y-2">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="À étudier"
          value={stats.a_etudier}
          candidateId={candidateId}
          stage="a_etudier"
          tone="bg-amber-50 text-amber-900 hover:border-amber-300"
        />
        <StatCard
          label="À postuler"
          value={stats.a_postuler}
          candidateId={candidateId}
          stage="a_postuler"
          tone="bg-emerald-50 text-emerald-900 hover:border-emerald-300"
        />
        <StatCard
          label="Postulé"
          value={stats.postule}
          candidateId={candidateId}
          stage="postule"
          tone="bg-slate-50 text-slate-700 hover:border-slate-400"
        />
      </div>
      <p className="text-sm text-slate-400">{stats.offres_total} offre(s) au total</p>
    </div>
  );
}

/** Carte-compteur, cliquable : ouvre Offres filtré sur l'étape d'entonnoir, pour ce candidat. */
function StatCard({
  label,
  value,
  candidateId,
  stage,
  tone,
}: {
  label: string;
  value: number;
  candidateId: string;
  stage: FunnelStage;
  tone: string;
}) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() =>
        navigate(`/offres?candidate=${encodeURIComponent(candidateId)}&stage=${stage}`)
      }
      className={`rounded-lg border border-slate-200 p-4 text-left transition-colors ${tone}`}
    >
      <p className="text-3xl font-semibold">{value}</p>
      <p className="mt-1 text-sm font-medium">{label}</p>
    </button>
  );
}
