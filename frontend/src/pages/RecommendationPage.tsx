import { Link, useLocation, useParams } from "react-router-dom";
import { ApiHttpError } from "../api/client";
import { useRecommendation } from "../api/recommendations";
import type { OfferAction, RecommendationDetail } from "../api/types";
import { ErrorNotice, Loading } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";

// Libellés FR de l'action auto figée (présentation seule — aucun statut inventé).
const ACTION_LABELS: Record<OfferAction, string> = {
  postuler: "Postuler",
  a_etudier: "À étudier",
  ignorer: "Ignorer",
  "": "—",
};

/**
 * Page /recommendations/:id — détail en lecture seule d'une recommandation (OPP-107).
 * Socle d'ancrage des actions à venir (validation OPP-108, candidature OPP-110).
 *
 * Le lien « retour » cible le run d'origine quand on arrive depuis sa liste (via
 * `location.state.from`) ; en deep-link direct, il retombe sur la liste des runs.
 */
export function RecommendationPage() {
  const { id = "" } = useParams();
  const location = useLocation();
  const backTo = (location.state as { from?: string } | null)?.from ?? "/";
  const { data, isPending, isError, error } = useRecommendation(id);

  const is404 = isError && error instanceof ApiHttpError && error.status === 404;

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-900">Recommandation</h2>
        <Link to={backTo} className="text-sm text-slate-500 hover:text-slate-900">
          ← Retour
        </Link>
      </div>

      {isPending && <Loading label="Chargement de la recommandation…" />}
      {is404 && (
        // Message neutre, anti-énumération : inexistant et hors périmètre sont indistincts.
        <p className="rounded-lg border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
          Recommandation introuvable ou inaccessible.
        </p>
      )}
      {isError && !is404 && <ErrorNotice error={error} />}

      {data && <RecommendationDetailView reco={data} />}
    </section>
  );
}

function RecommendationDetailView({ reco }: { reco: RecommendationDetail }) {
  return (
    <>
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            {/* title/company peuvent être null (offre disparue) → repli sur offer_id. */}
            <p className="font-medium text-slate-900">{reco.title || reco.offer_id}</p>
            <p className="text-sm text-slate-500">{reco.company || "—"}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="text-sm font-semibold text-slate-700">{reco.score}</span>
            <StatusBadge kind="decision" value={reco.status} />
          </div>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
          <Meta label="Action" value={ACTION_LABELS[reco.action]} />
          <Meta label="Candidat" value={reco.candidate_id} mono />
          <Meta label="Offre" value={reco.offer_id} mono />
        </dl>

        {reco.justification && (
          <p className="mt-4 text-sm text-slate-600">{reco.justification}</p>
        )}
        {reco.comment && (
          <p className="mt-3 rounded-md bg-slate-50 p-3 text-sm text-slate-700">
            <span className="font-medium">Commentaire : </span>
            {reco.comment}
          </p>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Historique de décision
        </h3>
        {reco.history.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
            Aucun événement.
          </p>
        ) : (
          <ol className="space-y-2">
            {reco.history.map((event, i) => (
              <li
                key={i}
                className="flex items-start justify-between gap-4 rounded-lg border border-slate-200 bg-white p-3"
              >
                <div className="flex items-center gap-2">
                  <StatusBadge kind="decision" value={event.status} />
                  {event.comment && (
                    <span className="text-sm text-slate-600">{event.comment}</span>
                  )}
                </div>
                <span className="shrink-0 text-xs text-slate-400">{formatDate(event.at)}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </>
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
