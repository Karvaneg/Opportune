import { Link, useParams } from "react-router-dom";
import { useRunDetail } from "../api/runs";
import { RunRecommendations } from "../components/RunRecommendations";
import { ErrorNotice, Loading } from "../components/States";

/**
 * Page /runs/:runId — métadonnées du run + **une seule** liste d'offres (OPP-149).
 *
 * On n'affiche plus la section « Évaluations » (instantané figé de `GET /runs/{id}`) en
 * parallèle des recommandations paginées : les deux se recouvraient et pouvaient se
 * contredire (le decision_status figé au run-time vs le courant). `RunRecommendations`
 * porte l'unique liste, avec un decision_status **résolu au courant** et des offres
 * cliquables. Le détail de `GET /runs/{id}` sert ici uniquement l'en-tête (candidat, date,
 * volumétrie, erreurs).
 */
export function RunDetailPage() {
  const { runId = "" } = useParams();
  const { data, isPending, isError, error } = useRunDetail(runId);

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-900">
          Run <span className="font-mono text-base text-slate-600">{runId}</span>
        </h2>
        <Link to="/" className="text-sm text-slate-500 hover:text-slate-900">
          ← Changer de run
        </Link>
      </div>

      {isPending && <Loading label="Chargement du run…" />}
      {isError && <ErrorNotice error={error} />}

      {data && (
        <>
          <dl className="grid grid-cols-2 gap-4 rounded-lg border border-slate-200 bg-white p-4 text-sm sm:grid-cols-3">
            <Meta label="Candidat" value={data.candidate_id} mono />
            <Meta label="Exécuté le" value={formatDate(data.executed_at)} />
            <Meta label="Offres évaluées" value={String(data.evaluations.length)} />
          </dl>

          {data.errors.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              <p className="font-medium">Erreurs pendant l'exécution</p>
              <ul className="mt-1 list-inside list-disc">
                {data.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Recommandations
            </h3>
            <RunRecommendations key={runId} runId={runId} />
            {/* key={runId} : remonte le composant à chaque changement de run → l'état de
                pagination/filtres repart à zéro, aucune reco d'un run précédent ne persiste. */}
          </div>
        </>
      )}
    </section>
  );
}

function Meta({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={`mt-0.5 text-slate-900 ${mono ? "font-mono text-xs" : ""}`}>{value}</dd>
    </div>
  );
}

/** Formatage tolérant : si la date n'est pas parsable, on affiche la valeur brute. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("fr-FR");
}
