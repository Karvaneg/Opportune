import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiHttpError } from "../api/client";
import {
  useConfirmApplication,
  useRecommendation,
  useValidateRecommendation,
  type DecisionVerb,
} from "../api/recommendations";
import { useIsReviewer } from "../auth/roles";
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

// Boutons de validation humaine (OPP-108) : verbe du contrat back + libellé + ton.
const VERB_BUTTONS: { verb: DecisionVerb; label: string; tone: string }[] = [
  { verb: "approve", label: "Approuver", tone: "bg-emerald-600 hover:bg-emerald-700" },
  { verb: "reject", label: "Rejeter", tone: "bg-red-600 hover:bg-red-700" },
  { verb: "defer", label: "Reporter", tone: "bg-amber-600 hover:bg-amber-700" },
];

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

      <RecommendationActions recommendationId={reco.recommendation_id} />
      <ApplicationConfirm recommendationId={reco.recommendation_id} />

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

/**
 * Panneau de validation humaine (OPP-108) — visible pour les reviewers uniquement.
 * Les verbes mappent le contrat back ; le succès invalide le détail (via le hook) donc
 * `status` et historique se rafraîchissent en direct. Le back reste l'autorité finale
 * (403 en dernier recours) si la garde UI est contournée.
 */
function RecommendationActions({ recommendationId }: { recommendationId: string }) {
  const isReviewer = useIsReviewer();
  const [comment, setComment] = useState("");
  const validate = useValidateRecommendation(recommendationId);

  // Garde reviewer côté UI (OPP-106) : contrôles masqués pour les autres rôles. Défense en
  // profondeur — le back conserve le 403 si la garde est contournée.
  if (!isReviewer) return null;

  const submit = (decision: DecisionVerb) =>
    validate.mutate(
      { decision, comment: comment.trim() || undefined },
      { onSuccess: () => setComment("") },
    );

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Validation
      </h3>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Commentaire (optionnel)"
        rows={2}
        aria-label="Commentaire"
        className="w-full rounded-md border border-slate-300 p-2 text-sm"
      />
      <div className="mt-3 flex flex-wrap gap-2">
        {VERB_BUTTONS.map(({ verb, label, tone }) => (
          <button
            key={verb}
            type="button"
            onClick={() => submit(verb)}
            disabled={validate.isPending}
            className={`rounded-md px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 ${tone}`}
          >
            {label}
          </button>
        ))}
      </div>
      {validate.isError && (
        <div className="mt-3">
          <ErrorNotice error={validate.error} />
        </div>
      )}
    </div>
  );
}

/**
 * Confirmation explicite d'une candidature (OPP-110) — reviewers uniquement. Double
 * consentement via modale : ouvrir ne déclenche rien ; seule la confirmation POST l'action.
 * Le 409 (« décision approuvée requise ») et l'idempotence (`already_confirmed`) sont
 * rendus lisibles. Exécution simulée à ce stade.
 */
function ApplicationConfirm({ recommendationId }: { recommendationId: string }) {
  const isReviewer = useIsReviewer();
  const [open, setOpen] = useState(false);
  const confirm = useConfirmApplication(recommendationId);

  if (!isReviewer) return null;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Candidature
      </h3>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={confirm.isPending}
        className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50"
      >
        Candidater…
      </button>

      {confirm.data && (
        <p className="mt-3 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">
          {confirm.data.already_confirmed
            ? "Candidature déjà confirmée"
            : "Candidature confirmée"}{" "}
          — statut : {confirm.data.status}.
        </p>
      )}
      {confirm.isError && (
        <div className="mt-3">
          <ErrorNotice error={confirm.error} />
        </div>
      )}

      {open && (
        <div
          role="dialog"
          aria-label="Confirmer la candidature"
          className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/30 p-4"
        >
          <div className="w-full max-w-sm rounded-lg bg-white p-5 shadow-lg">
            <p className="text-sm text-slate-700">
              Confirmer l'intention de candidater à cette offre ? L'action est explicite et
              requiert une décision préalablement approuvée.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              >
                Annuler
              </button>
              <button
                type="button"
                disabled={confirm.isPending}
                // onSettled : on referme dans tous les cas ; le résultat (succès ou 409)
                // s'affiche dans le panneau, jamais masqué derrière la modale.
                onClick={() => confirm.mutate(undefined, { onSettled: () => setOpen(false) })}
                className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Confirmer la candidature
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
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
