import { useState } from "react";
import { useCollectOffers } from "../api/offers";
import { useIsReviewer } from "../auth/roles";
import type { CollectionReport } from "../api/types";
import { ErrorNotice } from "./States";

/**
 * Récupère de nouvelles offres réelles depuis Adzuna (`POST /collect`, OPP-167) — reviewer
 * uniquement (curation du pool partagé). Un champ de recherche (mots-clés + lieu) cible la
 * passe ; le back l'exécute **de façon synchrone** et renvoie un bilan (collectées / nouvelles
 * / doublons). La passe fait un passage LLM par offre neuve → latence (« Récupération en
 * cours… »). Au succès, le catalogue est invalidé (cf. `useCollectOffers`) : les nouvelles
 * offres apparaissent dans la liste. Une panne de la source (identifiants manquants, quota)
 * revient dans `source_error` du bilan, pas en erreur HTTP — on l'affiche distinctement.
 */
// Poste recherché par défaut (OPP-167). Le profil décrit les compétences du candidat mais
// pas l'intitulé de poste visé, et les skills bruts font de mauvais mots-clés Adzuna : on
// préremplit donc un libellé métier large, modifiable. À remplacer par un champ « poste cible »
// du profil le jour où il existera (cf. ticket scoring/profil).
const DEFAULT_WHAT = "développeur informatique, web, d'application";

export function CollectOffers() {
  const isReviewer = useIsReviewer();
  const [what, setWhat] = useState(DEFAULT_WHAT);
  const [where, setWhere] = useState("");
  const collect = useCollectOffers();

  if (!isReviewer) return null;

  const submit = () => collect.mutate({ what: what.trim(), where: where.trim() });

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        Récupérer de nouvelles offres
      </h3>
      <p className="text-sm text-slate-500">
        Interroge Adzuna et ajoute les offres neuves au catalogue. Le poste recherché est
        prérempli (modifiable) ; précise un lieu pour cibler, ou laisse vide pour toute la France.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={what}
          onChange={(e) => setWhat(e.target.value)}
          placeholder="Poste recherché (ex. développeur web)"
          aria-label="Poste recherché"
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        />
        <input
          type="text"
          value={where}
          onChange={(e) => setWhere(e.target.value)}
          placeholder="Lieu (ex. Bordeaux)"
          aria-label="Lieu de recherche"
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={collect.isPending}
          className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50"
        >
          {collect.isPending ? "Récupération en cours…" : "Récupérer de nouvelles offres"}
        </button>
        {collect.data && <CollectSummary report={collect.data} />}
      </div>
      {collect.isError && <ErrorNotice error={collect.error} />}
    </div>
  );
}

/**
 * Bilan d'une passe affiché à côté du bouton. Une `source_error` (panne de la source) prime
 * sur les compteurs : même si HTTP 200, la passe n'a rien rapporté d'utile — on le dit
 * clairement plutôt que d'annoncer « 0 nouvelle » comme un résultat normal.
 */
function CollectSummary({ report }: { report: CollectionReport }) {
  if (report.source_error) {
    return (
      <span className="text-sm text-rose-700">
        Collecte impossible : {report.source_error}
      </span>
    );
  }
  return (
    <span className="text-sm text-emerald-700">
      {report.stored} nouvelle{report.stored > 1 ? "s" : ""} offre
      {report.stored > 1 ? "s" : ""} · {report.collected} collectée
      {report.collected > 1 ? "s" : ""} · {report.duplicates} doublon
      {report.duplicates > 1 ? "s" : ""}
      {report.failures > 0 && ` · ${report.failures} échec${report.failures > 1 ? "s" : ""}`}
      {report.enriched > 0 &&
        ` · ${report.enriched} enrichie${report.enriched > 1 ? "s" : ""} (${report.enriched_recovered} récupérée${report.enriched_recovered > 1 ? "s" : ""})`}
    </span>
  );
}
