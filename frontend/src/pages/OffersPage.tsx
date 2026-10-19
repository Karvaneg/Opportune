import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAddOffer, useEvaluateOffer, useOffers } from "../api/offers";
import { useAuth } from "../auth/AuthContext";
import { useIsReviewer } from "../auth/roles";
import type { CatalogOffer, OfferKind, RecommendationAction } from "../api/types";
import { Pager } from "../components/Pager";
import { ErrorNotice, Loading } from "../components/States";

/**
 * Catalogue des offres (GET /offers, OPP-146) : toutes les offres du pool, plus récentes
 * d'abord (tri serveur OPP-152), paginées. Un sélecteur de candidat annote chaque offre de
 * son **score de match** pour ce candidat (owner-gated côté API). Complète les runs : ici on
 * voit tout le stock, pas seulement les offres évaluées par un run.
 */
export function OffersPage() {
  const { identity } = useAuth();
  const candidates = identity?.owned_candidate_ids ?? [];
  // Candidat ciblé pour le score. Défaut : le 1er du périmètre → on voit un score d'emblée.
  const [candidate, setCandidate] = useState(candidates[0] ?? "");
  const [page, setPage] = useState(1);
  const target = candidates.includes(candidate) ? candidate : candidates[0] ?? "";
  const { data, isPending, isError, error, isFetching } = useOffers(page, target);

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold text-slate-900">Offres</h2>
        {candidates.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-slate-500">
            Score pour
            <select
              aria-label="Candidat pour le score de match"
              value={target}
              onChange={(e) => {
                setCandidate(e.target.value);
                setPage(1);
              }}
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

      <AddOffer />

      {isPending && <Loading label="Chargement des offres…" />}
      {isError && <ErrorNotice error={error} />}

      {!isError &&
        data &&
        (data.total === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
            Aucune offre dans le catalogue. Ajoute-en une ci-dessus.
          </p>
        ) : (
          <div className="space-y-3">
            <ul className="space-y-2">
              {data.items.map((offer) => (
                <OfferRow key={offer.id} offer={offer} candidateId={target} />
              ))}
            </ul>
            <Pager
              page={data.page}
              totalPages={data.total_pages}
              total={data.total}
              onPrev={() => setPage((p) => Math.max(1, p - 1))}
              onNext={() => setPage((p) => p + 1)}
              busy={isFetching}
            />
          </div>
        ))}
    </section>
  );
}

/**
 * Ajoute une offre au catalogue, par texte collé (OPP-145) ou par URL (OPP-148) — reviewer
 * uniquement (curation du pool partagé). Le back l'analyse via LLM (latence → « Ajout en
 * cours… »). Au succès, le catalogue est invalidé (cf. `useAddOffer`) : la nouvelle offre
 * apparaît dans la liste ci-dessous. Déplacé ici depuis « Runs » (OPP-161).
 */
function AddOffer() {
  const isReviewer = useIsReviewer();
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const add = useAddOffer();

  if (!isReviewer) return null;

  // Le texte prime (comme côté back) ; sinon on envoie l'URL. Un seul des deux suffit.
  const canSubmit = text.trim() !== "" || url.trim() !== "";
  const submit = () => {
    const variables = text.trim() !== "" ? { text } : { url };
    add.mutate(variables, {
      onSuccess: () => {
        setText("");
        setUrl("");
      },
    });
  };

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        Ajouter une offre
      </h3>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Colle ici le texte d'une offre d'emploi…"
        rows={5}
        aria-label="Texte de l'offre"
        className="w-full rounded-md border border-slate-300 p-2 text-sm"
      />
      <div className="flex items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-slate-400">ou</span>
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://… (URL d'une offre)"
          aria-label="URL de l'offre"
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={add.isPending || !canSubmit}
          className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50"
        >
          {add.isPending ? "Ajout en cours…" : "Ajouter l'offre"}
        </button>
        {add.data && (
          <span className="text-sm text-emerald-700">
            Offre ajoutée : {add.data.title} — {add.data.company}. Elle apparaît dans le
            catalogue ci-dessous.
          </span>
        )}
      </div>
      {add.isError && <ErrorNotice error={add.error} />}
    </div>
  );
}

/**
 * Ligne de catalogue. Le **titre ouvre la fiche interne** de l'offre pour le candidat ciblé
 * (OPP-160) : on évalue l'offre à la volée (get-or-create, sans run) puis on navigue vers sa
 * recommandation. Plus besoin de passer par un run. Le lien « voir sur le site » reste
 * accessible en **secondaire**. Sans candidat ciblé, le titre n'est plus cliquable (texte
 * brut) ; l'offre externe reste joignable via ce lien secondaire.
 */
function OfferRow({ offer, candidateId }: { offer: CatalogOffer; candidateId: string }) {
  const navigate = useNavigate();
  const evaluate = useEvaluateOffer();

  const openFiche = () =>
    evaluate.mutate(
      { candidateId, offerId: offer.id },
      {
        onSuccess: (reco) =>
          navigate(`/recommendations/${encodeURIComponent(reco.recommendation_id)}`, {
            // Le « ← Retour » de la fiche revient aux Offres (pas à la home Runs par défaut).
            state: { from: "/offres" },
          }),
      },
    );

  return (
    <li className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white p-4 hover:border-slate-400">
      <div className="min-w-0 flex-1">
        {candidateId ? (
          <button
            type="button"
            onClick={openFiche}
            disabled={evaluate.isPending}
            className="block w-full truncate text-left font-medium text-slate-900 hover:underline disabled:opacity-60"
          >
            {offer.title}
          </button>
        ) : (
          <p className="truncate font-medium text-slate-900">{offer.title}</p>
        )}
        <p className="truncate text-sm text-slate-500">
          {offer.company} · {offer.location} · {offer.contract_type} ·{" "}
          {formatDate(offer.created_at)}
        </p>
        {evaluate.isError && (
          <div className="mt-2">
            <ErrorNotice error={evaluate.error} />
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3 text-sm">
        {offer.url && (
          <a
            href={offer.url}
            target="_blank"
            rel="noreferrer"
            className="text-slate-400 hover:text-slate-600 hover:underline"
            title="Voir l'offre sur le site"
          >
            voir sur le site ↗
          </a>
        )}
        <span className="text-slate-400">{offer.source}</span>
        <ScoreBadge kind={offer.kind} score={offer.score} action={offer.action} />
      </div>
    </li>
  );
}

// Couleur du badge par bande de reco (seuils décidés côté serveur, cf. `RecommendationAction`).
const SCORE_TONES: Record<RecommendationAction, string> = {
  postuler: "bg-emerald-100 text-emerald-800",
  a_etudier: "bg-amber-100 text-amber-800",
  ignorer: "bg-slate-100 text-slate-600",
};

/**
 * Badge de score de match. Une **formation** (OPP-166) n'est pas scorée : on affiche un badge
 * « Formation » explicite (jamais 0 ni le tiret ambigu). Sinon : la bande de reco colore le
 * score ; `null` (non ciblé / non évaluable pour un emploi) → tiret neutre.
 */
function ScoreBadge({
  kind,
  score,
  action,
}: {
  kind: OfferKind;
  score: number | null;
  action: RecommendationAction | null;
}) {
  if (kind === "formation") {
    return (
      <span
        className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-800"
        title="Formation : non évaluée sur l'adéquation (son but est d'acquérir des compétences)"
      >
        Formation
      </span>
    );
  }
  if (score === null || action === null) {
    return <span className="text-slate-400" title="Non évalué">—</span>;
  }
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SCORE_TONES[action]}`}>
      {score}/100
    </span>
  );
}

/** Formatage tolérant : valeur brute si la date n'est pas parsable. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("fr-FR");
}
