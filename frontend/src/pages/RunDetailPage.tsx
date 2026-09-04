import { Link, useParams } from "react-router-dom";
import { useRunDetail } from "../api/runs";
import type { RunEvaluation } from "../api/types";
import { RunRecommendations } from "../components/RunRecommendations";
import { ErrorNotice, Loading } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";

/** Page /runs/:runId — métadonnées, évaluations, erreurs, puis reco paginées. */
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
              Évaluations
            </h3>
            {data.evaluations.length === 0 ? (
              <EmptyState label="Aucune offre évaluée dans ce run." />
            ) : (
              <ul className="space-y-2">
                {data.evaluations.map((evaluation) => (
                  <EvaluationRow key={evaluation.offer_id} evaluation={evaluation} />
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Recommandations (paginées)
            </h3>
            <RunRecommendations key={runId} runId={runId} />
            {/* key={runId} : remonte le composant à chaque changement de run → l'état de
                pagination repart à 1 et aucune reco d'un run précédent ne persiste. */}
          </div>
        </>
      )}
    </section>
  );
}

function EvaluationRow({ evaluation }: { evaluation: RunEvaluation }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-medium text-slate-900">{evaluation.title || evaluation.offer_id}</p>
          <p className="text-sm text-slate-500">{evaluation.company || "—"}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-sm font-semibold text-slate-700">{evaluation.score}</span>
          <StatusBadge kind="advisory" value={evaluation.advisory_status} />
          <StatusBadge kind="decision" value={evaluation.decision_status} />
        </div>
      </div>
      {evaluation.justification && (
        <p className="mt-2 text-sm text-slate-600">{evaluation.justification}</p>
      )}
    </li>
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

function EmptyState({ label }: { label: string }) {
  return (
    <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
      {label}
    </p>
  );
}

/** Formatage tolérant : si la date n'est pas parsable, on affiche la valeur brute. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("fr-FR");
}
