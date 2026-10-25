import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  activeCollectKey,
  offerKeys,
  useActiveCollectJob,
  useCollectJob,
  useStartCollect,
} from "../api/offers";
import { useIsReviewer } from "../auth/roles";
import type { CollectionProgress, CollectionReport } from "../api/types";
import { CollectCounts } from "./CollectCounts";
import { ErrorNotice } from "./States";

/**
 * Récupère de nouvelles offres réelles depuis Adzuna (`POST /collect`, OPP-170) — reviewer
 * uniquement (curation du pool partagé). Un champ de recherche (mots-clés + lieu) cible la
 * passe ; le back l'exécute **de façon asynchrone** : le démarrage rend la main aussitôt avec
 * un `job_id`, puis on **sonde** l'avancement (`GET /collect/{job_id}`) jusqu'au bilan. La passe
 * fait un passage LLM par offre neuve → plusieurs minutes, suivies en direct (compteurs de
 * progression). À la complétion, si des offres ont été persistées, le catalogue est invalidé :
 * les nouvelles offres apparaissent sans rechargement. Une panne de la source (identifiants
 * manquants, quota) revient dans `source_error` du bilan, pas en erreur HTTP — on l'affiche
 * distinctement ; un `409` au démarrage signale qu'une collecte est déjà en cours.
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
  const [jobId, setJobId] = useState<string | null>(null);
  const start = useStartCollect();
  const job = useCollectJob(jobId);
  // Suivi global (OPP-208) : une collecte peut tourner même si elle a été lancée depuis un autre
  // écran (le `jobId` local serait alors nul). On s'en sert pour verrouiller le bouton.
  const active = useActiveCollectJob();
  const queryClient = useQueryClient();
  // Mémorise le job déjà pris en compte pour n'invalider le catalogue qu'une fois à sa fin.
  const invalidatedFor = useRef<string | null>(null);

  const status = job.data?.status;
  // Un job lancé mais pas encore terminé compte comme « en cours », même avant le premier
  // sondage (où `status` est encore `undefined`) : sinon le bouton se réactiverait dans cette
  // fenêtre et un second clic déclencherait un `POST /collect` → 409 (unicité) affiché à côté
  // du job légitime qui progresse.
  const running =
    start.isPending ||
    active.data?.job?.status === "running" ||
    (jobId !== null && status !== "done" && status !== "failed");

  // À la complétion d'un job ayant persisté des offres, rafraîchir le catalogue — une seule
  // fois par job (une passe de doublons ou en échec de source ne change rien au catalogue).
  useEffect(() => {
    if (!jobId || status !== "done" || invalidatedFor.current === jobId) return;
    invalidatedFor.current = jobId;
    if ((job.data?.report?.stored ?? 0) > 0) {
      queryClient.invalidateQueries({ queryKey: offerKeys.all });
    }
  }, [jobId, status, job.data, queryClient]);

  if (!isReviewer) return null;

  const submit = () =>
    start.mutate(
      { what: what.trim(), where: where.trim() },
      {
        onSuccess: (data) => {
          setJobId(data.job_id);
          // Allume l'indicateur global sans attendre le prochain sondage (OPP-208).
          queryClient.invalidateQueries({ queryKey: activeCollectKey });
        },
      },
    );

  return (
    <div className="space-y-3 rounded-lg border border-border bg-surface-raised p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Récupérer de nouvelles offres
      </h3>
      <p className="text-sm text-ink-muted">
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
          className="min-w-0 flex-1 rounded-md border border-border px-3 py-1.5 text-sm"
        />
        <input
          type="text"
          value={where}
          onChange={(e) => setWhere(e.target.value)}
          placeholder="Lieu (ex. Bordeaux)"
          aria-label="Lieu de recherche"
          className="min-w-0 flex-1 rounded-md border border-border px-3 py-1.5 text-sm"
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={running}
          className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
        >
          {running ? "Récupération en cours…" : "Récupérer de nouvelles offres"}
        </button>
        {status === "running" && job.data && <CollectProgress progress={job.data.progress} />}
        {status === "done" && job.data?.report && <CollectSummary report={job.data.report} />}
        {status === "failed" && (
          <span className="text-sm text-danger">
            Collecte échouée : {job.data?.error ?? "erreur inconnue"}
          </span>
        )}
      </div>
      {start.isError && <ErrorNotice error={start.error} />}
      {job.isError && <ErrorNotice error={job.error} />}
    </div>
  );
}

/**
 * Avancement d'une passe en cours, affiché à côté du bouton pendant le sondage. Donne le
 * ressenti de progression sur une collecte longue (plusieurs minutes), avant le bilan final.
 */
function CollectProgress({ progress }: { progress: CollectionProgress }) {
  return (
    <span className="text-sm text-ink-muted">
      Récupération… <CollectCounts progress={progress} />
    </span>
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
      <span className="text-sm text-danger">
        Collecte impossible : {report.source_error}
      </span>
    );
  }
  return (
    <span className="text-sm text-success-text">
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
