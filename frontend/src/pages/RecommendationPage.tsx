import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiHttpError } from "../api/client";
import {
  useConfirmApplication,
  useMarkApplied,
  useRecommendation,
  useRescoreOffer,
  useUnmarkApplied,
  useValidateRecommendation,
  type DecisionVerb,
} from "../api/recommendations";
import {
  useDeleteLetter,
  useEditLetter,
  useGenerateLetter,
  useLetter,
} from "../api/letters";
import { useIsReviewer } from "../auth/roles";
import type {
  ApplicationIntent,
  DecisionHistoryEvent,
  DecisionStatus,
  Letter,
  OfferAction,
  RecommendationDetail,
} from "../api/types";
import { ErrorNotice, Loading } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";

// Libellés FR de l'action auto figée (présentation seule — aucun statut inventé).
const ACTION_LABELS: Record<OfferAction, string> = {
  postuler: "Postuler",
  a_etudier: "À étudier",
  ignorer: "Ignorer",
  indeterminee: "À évaluer", // formation (OPP-166) ou données insuffisantes : aucune pré-reco auto
  "": "—",
};

// Boutons de validation humaine (OPP-108) : verbe du contrat back + libellé + ton.
const VERB_BUTTONS: { verb: DecisionVerb; label: string; tone: string }[] = [
  { verb: "approve", label: "Approuver", tone: "bg-success hover:bg-success-strong" },
  { verb: "reject", label: "Rejeter", tone: "bg-danger hover:bg-danger-strong" },
  { verb: "defer", label: "Reporter", tone: "bg-warning hover:bg-warning-strong" },
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
        <h2 className="text-xl font-semibold text-ink">Recommandation</h2>
        <Link to={backTo} className="text-sm text-ink-muted hover:text-ink">
          ← Retour
        </Link>
      </div>

      {isPending && <Loading label="Chargement de la recommandation…" />}
      {is404 && (
        // Message neutre, anti-énumération : inexistant et hors périmètre sont indistincts.
        <p className="rounded-lg border border-border bg-surface-raised p-6 text-center text-sm text-ink-muted">
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
      <div className="rounded-lg border border-border bg-surface-raised p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            {/* title/company peuvent être null (offre disparue) → repli sur offer_id. */}
            <p className="font-medium text-ink">{reco.title || reco.offer_id}</p>
            <p className="text-sm text-ink-muted">{reco.company || "—"}</p>
            {/* Lien vers l'annonce d'origine (OPP-112), si l'offre en porte une. */}
            {reco.url && (
              <a
                href={reco.url}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-block text-sm text-ink-muted hover:text-ink hover:underline"
                title="Voir l'offre sur le site"
              >
                voir sur le site ↗
              </a>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {/* Une formation (OPP-166) n'a pas de score d'adéquation : badge explicite plutôt
                qu'un chiffre (fiche historique antérieure à la distinction emploi/formation).
                `score` peut aussi être `null` sans que `kind` soit « formation » (offre disparue
                → `kind === null`) : on retombe alors sur un tiret neutre, jamais un vide. */}
            {reco.kind === "formation" ? (
              <span
                className="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand"
                title="Formation : non évaluée sur l'adéquation (son but est d'acquérir des compétences)"
              >
                Formation
              </span>
            ) : reco.score === null ? (
              <span className="text-sm font-semibold text-ink-muted" title="Non évalué">
                —
              </span>
            ) : (
              <span className="text-sm font-semibold text-ink">{reco.score}</span>
            )}
            <StatusBadge kind="decision" value={reco.status} />
          </div>
        </div>

        {/* Action · Recherche · Offre · Ajoutée le sur une seule ligne (4 colonnes dès sm). */}
        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <Meta label="Action" value={ACTION_LABELS[reco.action]} />
          <Meta label="Recherche" value={reco.candidate_id} mono />
          <Meta label="Offre" value={reco.offer_id} mono />
          {/* Date d'ingestion de l'offre dans Opportune (OPP-112), si connue. */}
          {reco.created_at && <Meta label="Ajoutée le" value={formatDay(reco.created_at)} />}
        </dl>

        {reco.justification && (
          <p className="mt-4 text-sm text-ink-muted">{reco.justification}</p>
        )}
        {reco.comment && (
          <p className="mt-3 rounded-md bg-surface p-3 text-sm text-ink">
            <span className="font-medium">Commentaire : </span>
            {reco.comment}
          </p>
        )}
      </div>

      <RescoreOffer reco={reco} />
      <LetterPanel recommendationId={reco.recommendation_id} />
      <RecommendationActions recommendationId={reco.recommendation_id} />
      <ApplicationConfirm
        recommendationId={reco.recommendation_id}
        application={reco.application}
      />

      <DecisionTimeline history={reco.history} application={reco.application} />
    </>
  );
}

/**
 * Historique unifié : fusionne **à l'affichage** les événements de décision humaine
 * (`history`) et les jalons de candidature (`application`) dans une seule frise triée par
 * date. On ne mélange pas les modèles côté back (décision ≠ action) — c'est une agrégation de
 * présentation. L'intention/candidature reflètent l'état courant : annuler une candidature la
 * retire aussi de la frise.
 */
function DecisionTimeline({
  history,
  application,
}: {
  history: DecisionHistoryEvent[];
  application: ApplicationIntent | null;
}) {
  type Item =
    | { at: string; kind: "decision"; status: DecisionStatus; comment: string | null }
    | { at: string; kind: "intent" | "applied" };

  const items: Item[] = [
    ...history.map(
      (e): Item => ({ at: e.at, kind: "decision", status: e.status, comment: e.comment }),
    ),
  ];
  if (application?.confirmed) {
    items.push({ at: application.confirmed_at, kind: "intent" });
  }
  if (application?.applied && application.applied_at) {
    items.push({ at: application.applied_at, kind: "applied" });
  }
  // Tri chronologique ascendant (dates ISO) ; ordre d'insertion préservé à égalité de date.
  // `parseIsoDate` traite les dates seules en heure locale (sinon elles se classent à minuit
  // UTC, donc potentiellement le mauvais jour face aux timestamps de décision).
  items.sort((a, b) => parseIsoDate(a.at).getTime() - parseIsoDate(b.at).getTime());

  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Historique
      </h3>
      {items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border bg-surface-raised p-6 text-center text-sm text-ink-muted">
          Aucun événement.
        </p>
      ) : (
        <ol className="space-y-2">
          {items.map((item, i) => (
            <li
              key={i}
              className="flex items-start justify-between gap-4 rounded-lg border border-border bg-surface-raised p-3"
            >
              <div className="flex items-center gap-2">
                {item.kind === "decision" ? (
                  <>
                    <StatusBadge kind="decision" value={item.status} />
                    {item.comment && (
                      <span className="text-sm text-ink-muted">{item.comment}</span>
                    )}
                  </>
                ) : (
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      item.kind === "applied"
                        ? "bg-success/15 text-success-text"
                        : "bg-brand/10 text-brand"
                    }`}
                  >
                    {item.kind === "applied"
                      ? "Candidature effectuée"
                      : "Intention de candidater notée"}
                  </span>
                )}
              </div>
              <span className="shrink-0 text-xs text-ink-muted">{formatDate(item.at)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/**
 * Re-score ciblé d'une offre (OPP-150) — proposé **uniquement tant que l'offre n'est pas
 * arbitrée** (`status === "pending"`). Un run n'évalue plus que les offres nouvelles ; ce
 * bouton permet de recalculer à la demande le score d'une offre ancienne (p. ex. après mise
 * à jour du profil). Une offre déjà tranchée est figée → bouton absent (le back préserve de
 * toute façon la décision humaine). Au succès, le score affiché se rafraîchit (invalidation
 * du détail). Action de propriétaire (pas réservée aux reviewers), comme lancer un run.
 */
function RescoreOffer({ reco }: { reco: RecommendationDetail }) {
  const rescore = useRescoreOffer(reco.recommendation_id, reco.candidate_id, reco.offer_id);

  if (reco.status !== "pending") return null;

  return (
    <div className="rounded-lg border border-border bg-surface-raised p-4">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Re-score
      </h3>
      <p className="mb-3 text-sm text-ink-muted">
        Recalculer le score de cette offre (p. ex. après mise à jour du profil).
      </p>
      <button
        type="button"
        onClick={() => rescore.mutate()}
        disabled={rescore.isPending}
        className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface disabled:opacity-50"
      >
        {rescore.isPending ? "Re-score en cours…" : "Re-scorer l'offre"}
      </button>
      {rescore.isError && (
        <div className="mt-3">
          <ErrorNotice error={rescore.error} />
        </div>
      )}
    </div>
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
    <div className="rounded-lg border border-border bg-surface-raised p-4">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Validation
      </h3>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Commentaire (optionnel)"
        rows={2}
        aria-label="Commentaire"
        className="w-full rounded-md border border-border p-2 text-sm"
      />
      <div className="mt-3 flex flex-wrap gap-2">
        {VERB_BUTTONS.map(({ verb, label, tone }) => (
          <button
            key={verb}
            type="button"
            onClick={() => submit(verb)}
            disabled={validate.isPending}
            className={`rounded-md px-3 py-1.5 text-sm font-medium text-on-brand disabled:opacity-50 ${tone}`}
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
 * Note d'une **intention de candidater** (OPP-110) — reviewers uniquement. Double consentement
 * via modale : ouvrir ne déclenche rien ; seule la confirmation POST l'action. L'action
 * n'envoie **rien** vers l'extérieur (exécution simulée en V2) : elle trace que tu comptes
 * candidater. L'état est **persistant** — relu depuis `reco.application` au chargement — et
 * s'affiche même après rechargement. Le 409 (« décision approuvée requise ») reste lisible.
 */
function ApplicationConfirm({
  recommendationId,
  application,
}: {
  recommendationId: string;
  application: ApplicationIntent | null;
}) {
  const isReviewer = useIsReviewer();
  const [open, setOpen] = useState(false);
  // YYYY-MM-DD en **heure locale** (`en-CA` formate en ISO court) : `toISOString()` donnerait
  // la date UTC et pourrait proposer « demain » le soir pour un fuseau en retard sur UTC.
  const today = new Date().toLocaleDateString("en-CA"); // défaut + borne `max` du sélecteur
  const [appliedDate, setAppliedDate] = useState(today);
  const confirm = useConfirmApplication(recommendationId);
  const markApplied = useMarkApplied(recommendationId);
  const unmarkApplied = useUnmarkApplied(recommendationId);

  if (!isReviewer) return null;

  // Trois états du cycle de vie. L'intention est notée dès qu'elle est en base (au chargement)
  // ou tout juste confirmée dans la session ; de même, « candidaté » vaut dès que le back le
  // porte ou qu'on vient de le déclarer. `confirmed_at`/`applied_at` viennent de l'état
  // persistant (le détail est re-fetché après chaque POST, donc les dates arrivent au re-rendu).
  // Le flag optimiste `markApplied.data` est remis à zéro par l'annulation (`unmarkApplied` →
  // `markApplied.reset()`), sinon il resterait « collé » et masquerait le retour à l'intention.
  const notedAt = application?.confirmed_at ?? null;
  const appliedAt = application?.applied_at ?? null;
  const noted = application?.confirmed === true || (confirm.data != null && !confirm.isError);
  const applied =
    application?.applied === true || (markApplied.data != null && !markApplied.isError);

  return (
    <div className="rounded-lg border border-border bg-surface-raised p-4">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Candidature
      </h3>

      {applied ? (
        <div className="flex items-center justify-between gap-3 rounded-md bg-success/15 p-3">
          <p className="text-sm text-success-text">
            🎉 Tu as candidaté à cette offre
            {appliedAt ? ` — le ${formatDay(appliedAt)}` : ""}.
          </p>
          <button
            type="button"
            onClick={() => unmarkApplied.mutate(undefined, { onSuccess: () => markApplied.reset() })}
            disabled={unmarkApplied.isPending}
            aria-label="Annuler la candidature"
            title="Annuler la candidature (je n'ai pas candidaté)"
            className="shrink-0 text-lg font-bold leading-none text-danger hover:text-danger-strong disabled:opacity-50"
          >
            ✕
          </button>
        </div>
      ) : noted ? (
        <>
          <p className="rounded-md bg-success/10 p-3 text-sm text-success-text">
            ✅ Tu as noté que tu vas candidater à cette offre
            {notedAt ? ` — le ${formatDate(notedAt)}` : ""}.
            <span className="mt-1 block text-xs text-success-text">
              Aucun envoi n'est effectué : Opportune garde la trace de ton suivi.
            </span>
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="text-xs text-ink-muted">
              Date de candidature
              <input
                type="date"
                value={appliedDate}
                max={today}
                onChange={(e) => setAppliedDate(e.target.value)}
                aria-label="Date de candidature"
                className="mt-1 block rounded-md border border-border px-2 py-1 text-sm"
              />
            </label>
            <button
              type="button"
              onClick={() =>
                markApplied.mutate(
                  { applied_at: appliedDate },
                  { onSuccess: () => unmarkApplied.reset() },
                )
              }
              disabled={markApplied.isPending}
              className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
            >
              J'ai candidaté
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="mb-2 text-sm text-ink-muted">
            Marque que tu comptes candidater à cette offre. Opportune n'envoie rien à ta
            place : c'est un suivi de ton intention.
          </p>
          <button
            type="button"
            onClick={() => setOpen(true)}
            disabled={confirm.isPending}
            className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
          >
            Je vais candidater
          </button>
        </>
      )}

      {confirm.isError && (
        <div className="mt-3">
          <ErrorNotice error={confirm.error} />
        </div>
      )}
      {markApplied.isError && (
        <div className="mt-3">
          <ErrorNotice error={markApplied.error} />
        </div>
      )}
      {unmarkApplied.isError && (
        <div className="mt-3">
          <ErrorNotice error={unmarkApplied.error} />
        </div>
      )}

      {open && (
        <div
          role="dialog"
          aria-label="Confirmer l'intention de candidater"
          className="fixed inset-0 z-10 flex items-center justify-center bg-ink/30 p-4"
        >
          <div className="w-full max-w-sm rounded-lg bg-surface-raised p-5 shadow-lg">
            <p className="text-sm text-ink">
              Noter que tu as l'intention de candidater à cette offre ? Rien n'est envoyé —
              c'est un suivi. L'action requiert une décision préalablement approuvée.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md border border-border px-3 py-1.5 text-sm"
              >
                Annuler
              </button>
              <button
                type="button"
                disabled={confirm.isPending}
                // onSettled : on referme dans tous les cas ; le résultat (succès ou 409)
                // s'affiche dans le panneau, jamais masqué derrière la modale.
                onClick={() => confirm.mutate(undefined, { onSettled: () => setOpen(false) })}
                className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
              >
                Oui, je vais candidater
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Libellé FR de la provenance d'une lettre (présentation seule).
const LETTER_SOURCE_LABELS: Record<Letter["source"], string> = {
  ai: "Générée par l'IA",
  human: "Éditée à la main",
};

/**
 * Panneau lettre de motivation (OPP-147) — reviewers uniquement (contenu de candidature).
 * Trois états : aucune lettre (bouton Générer), lettre présente (corps + éditer / régénérer
 * / supprimer), édition en cours (zone de texte → PUT). La régénération d'une lettre existante
 * est un geste **explicite** : le back refuse (409) d'écraser en silence, donc l'UI demande
 * confirmation avant d'envoyer `{ regenerate: true }` — protégeant notamment une édition humaine.
 * Un 404 sur la lettre n'est pas une erreur : c'est l'état « pas encore générée ».
 */
function LetterPanel({ recommendationId }: { recommendationId: string }) {
  const isReviewer = useIsReviewer();
  const { data, isPending, isError, error } = useLetter(recommendationId);
  const generate = useGenerateLetter(recommendationId);
  const edit = useEditLetter(recommendationId);
  const remove = useDeleteLetter(recommendationId);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [confirmRegen, setConfirmRegen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Garde reviewer côté UI (défense en profondeur ; le back garde le 403/404).
  if (!isReviewer) return null;

  const is404 = isError && error instanceof ApiHttpError && error.status === 404;
  // Une lettre n'est « présente » que si la dernière requête a réussi et porte un corps
  // chaîne. `!isError` est crucial : React Query conserve `data` après un refetch en erreur
  // (ex. 404 déclenché par la suppression), donc sans ce garde l'ancienne lettre resterait
  // affichée — avec ses boutons actifs — à côté de l'état « aucune lettre ».
  const letter = !isError && data && typeof data.body === "string" ? data : null;

  const startEditing = () => {
    setDraft(letter?.body ?? "");
    setEditing(true);
  };
  const saveEdit = () =>
    edit.mutate(draft, { onSuccess: () => setEditing(false) });

  return (
    <div className="rounded-lg border border-border bg-surface-raised p-4">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Lettre de motivation
      </h3>

      {isPending && <Loading label="Chargement de la lettre…" />}
      {isError && !is404 && <ErrorNotice error={error} />}

      {/* Aucune lettre encore : proposer la génération. */}
      {(is404 || (!isPending && !isError && !letter)) && (
        <div>
          <p className="mb-3 text-sm text-ink-muted">
            Aucune lettre pour cette recommandation. Générez-en une à partir de l'offre et du
            profil.
          </p>
          <button
            type="button"
            onClick={() => generate.mutate({})}
            disabled={generate.isPending}
            className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
          >
            {generate.isPending ? "Génération en cours…" : "Générer la lettre"}
          </button>
          {generate.isError && (
            <div className="mt-3">
              <ErrorNotice error={generate.error} />
            </div>
          )}
        </div>
      )}

      {/* Lettre présente : corps + provenance + actions. */}
      {letter && !editing && (
        <div>
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded-full bg-ink/5 px-2 py-0.5 text-xs font-medium text-ink-muted">
              {LETTER_SOURCE_LABELS[letter.source]}
            </span>
          </div>
          <p className="whitespace-pre-wrap rounded-md bg-surface p-3 text-sm text-ink">
            {letter.body}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={startEditing}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface"
            >
              Éditer
            </button>
            <button
              type="button"
              onClick={() => setConfirmRegen(true)}
              disabled={generate.isPending}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-ink hover:bg-surface disabled:opacity-50"
            >
              {generate.isPending ? "Régénération…" : "Régénérer"}
            </button>
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              disabled={remove.isPending}
              className="rounded-md border border-danger/30 px-3 py-1.5 text-sm font-medium text-danger hover:bg-danger/10 disabled:opacity-50"
            >
              Supprimer
            </button>
          </div>
          {(generate.isError || remove.isError) && (
            <div className="mt-3">
              <ErrorNotice error={generate.error ?? remove.error} />
            </div>
          )}
        </div>
      )}

      {/* Édition en cours : zone de texte → PUT. */}
      {letter && editing && (
        <div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={10}
            aria-label="Corps de la lettre"
            className="w-full rounded-md border border-border p-2 text-sm"
          />
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={saveEdit}
              disabled={edit.isPending || draft.trim() === ""}
              className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
            >
              {edit.isPending ? "Enregistrement…" : "Enregistrer"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-md border border-border px-3 py-1.5 text-sm"
            >
              Annuler
            </button>
          </div>
          {edit.isError && (
            <div className="mt-3">
              <ErrorNotice error={edit.error} />
            </div>
          )}
        </div>
      )}

      {/* Confirmation de régénération : écrase la lettre actuelle (y compris une édition). */}
      {confirmRegen && (
        <ConfirmDialog
          label="Confirmer la régénération"
          message="Régénérer remplacera la lettre actuelle, y compris vos éventuelles modifications manuelles. Continuer ?"
          confirmLabel="Régénérer"
          onCancel={() => setConfirmRegen(false)}
          onConfirm={() =>
            generate.mutate(
              { regenerate: true },
              { onSettled: () => setConfirmRegen(false) },
            )
          }
        />
      )}

      {/* Confirmation de suppression. */}
      {confirmDelete && (
        <ConfirmDialog
          label="Confirmer la suppression"
          message="Supprimer définitivement la lettre de cette recommandation ?"
          confirmLabel="Supprimer"
          onCancel={() => setConfirmDelete(false)}
          onConfirm={() =>
            remove.mutate(undefined, { onSettled: () => setConfirmDelete(false) })
          }
        />
      )}
    </div>
  );
}

/** Petite modale de confirmation réutilisable (double consentement, cf. ApplicationConfirm). */
function ConfirmDialog({
  label,
  message,
  confirmLabel,
  onCancel,
  onConfirm,
}: {
  label: string;
  message: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-label={label}
      className="fixed inset-0 z-10 flex items-center justify-center bg-ink/30 p-4"
    >
      <div className="w-full max-w-sm rounded-lg bg-surface-raised p-5 shadow-lg">
        <p className="text-sm text-ink">{message}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-border px-3 py-1.5 text-sm"
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function Meta({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className={`mt-0.5 text-ink ${mono ? "font-mono text-xs" : ""}`}>{value}</dd>
    </div>
  );
}

/** Formatage tolérant : si la date n'est pas parsable, on affiche la valeur brute. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("fr-FR");
}

/**
 * Parse une date ISO en tolérant les dates **seules** (`YYYY-MM-DD`). `new Date("2026-10-03")`
 * les interprète en UTC (minuit UTC → jour décalé dans un fuseau en retard) ; on force l'heure
 * locale en complétant `T00:00:00` pour qu'elles s'ordonnent et s'affichent au bon jour.
 */
function parseIsoDate(iso: string): Date {
  return new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso);
}

/** Date **seule** (sans heure) — pour une date choisie par l'utilisateur (ex. candidature). */
function formatDay(iso: string): string {
  const d = parseIsoDate(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("fr-FR");
}
