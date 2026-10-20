import { Link, useNavigate } from "react-router-dom";
import { useCandidateActivity } from "../api/activity";
import { useCandidateStats } from "../api/stats";
import type { FunnelStage } from "../api/funnel";
import type { ActivityEvent } from "../api/types";
import { useTargetCandidate } from "../auth/useTargetCandidate";
import { AddOffer } from "../components/AddOffer";
import { LaunchRun } from "../components/LaunchRun";
import { ProfilePanel } from "../components/ProfilePanel";
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

      {/* Raccourcis d'action en haut, juste sous l'en-tête : « que puis-je faire maintenant ? »
          doit rester visible sans scroller sous le flux d'activité (OPP-165, retour dogfood). */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Nouvelle analyse
          </h3>
          <LaunchRun />
        </div>
        <AddOffer />
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
          <ActivityFeed candidateId={target} />
          <ProfilePanel candidateId={target} />
        </>
      )}
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
        {/* Couleurs alignées sur le parcours de candidature de la fiche reco : « à postuler »
            reprend l'indigo de « intention de candidater notée », « postulées » le vert de
            « candidature effectuée » (c'est fait). */}
        <StatCard
          label="À postuler"
          value={stats.a_postuler}
          candidateId={candidateId}
          stage="a_postuler"
          tone="bg-indigo-50 text-indigo-900 hover:border-indigo-300"
        />
        <StatCard
          label="Postulées"
          value={stats.postule}
          candidateId={candidateId}
          stage="postule"
          tone="bg-emerald-50 text-emerald-900 hover:border-emerald-300"
        />
      </div>
      <p className="text-sm text-slate-400">{stats.offres_total} offre(s) au total</p>
    </div>
  );
}

/**
 * Flux « Dernière activité » (OPP-165) : journal transversal horodaté sous les cartes. Chaque
 * événement est un lien vers sa cible (fiche de recommandation, ou catalogue pour une offre).
 */
function ActivityFeed({ candidateId }: { candidateId: string }) {
  const { data, isPending, isError, error } = useCandidateActivity(candidateId);

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        Dernières activités
      </h3>
      {isPending && <Loading label="Chargement de l'activité…" />}
      {isError && <ErrorNotice error={error} />}
      {data &&
        (data.items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-center text-sm text-slate-500">
            Aucune activité récente.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
            {data.items.map((event, i) => (
              <li key={`${event.target_id}-${event.at}-${i}`} className="px-4 py-2.5">
                <ActivityRow event={event} />
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}

function ActivityRow({ event }: { event: ActivityEvent }) {
  const to =
    event.target_kind === "recommendation"
      ? `/recommendations/${encodeURIComponent(event.target_id)}`
      : "/offres";
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <Link
        to={to}
        state={{ from: "/" }}
        className="min-w-0 flex-1 truncate text-slate-700 hover:text-slate-900 hover:underline"
      >
        {event.label}
      </Link>
      <span className="shrink-0 text-xs text-slate-400">{formatActivityDate(event.at)}</span>
    </div>
  );
}

/** Date lisible ; valeur brute si non parsable (robustesse). */
function formatActivityDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("fr-FR");
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
