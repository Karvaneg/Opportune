import { Link } from "react-router-dom";
import { useProfile } from "../api/profile";
import { useRuns } from "../api/runs";
import { useIsReviewer } from "../auth/roles";
import type { CandidateStats } from "../api/types";

/** Fait défiler jusqu'à un ancrage de la page, en douceur. Pur confort de navigation (pas de
 * logique métier) : sous jsdom, `scrollIntoView` n'existe pas, d'où le garde optionnel. */
function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView?.({ behavior: "smooth", block: "start" });
}

/** Une étape du guide : son libellé, son état, et l'action qui y mène — soit un lien vers une
 * autre page (`to`), soit un défilement intra-page (`onClick`). */
type Step = {
  title: string;
  description: string;
  done: boolean;
  action: { label: string; to: string } | { label: string; onClick: () => void };
};

/**
 * Guide d'accueil « Nouveau profil » (OPP-177) : transforme un cockpit vide en chemin clair.
 * Trois étapes — ajouter un CV, récupérer des offres, lancer une analyse — dont l'avancement se
 * **déduit de l'état réel** (profil, pool d'offres, runs du candidat), sans drapeau persistant.
 * Chaque étape à faire renvoie à l'action existante (navigation guidée, pas de duplication d'UI).
 * L'encart disparaît dès que la boucle de démarrage est complète.
 *
 * Réservé au **reviewer** : les trois étapes (importer un CV, curer le pool d'offres, lancer une
 * analyse) sont des actions de curation qu'un simple lecteur ne peut pas mener à bien.
 */
export function NewProfileGuide({
  candidateId,
  stats,
}: {
  candidateId: string;
  stats: CandidateStats | undefined;
}) {
  const isReviewer = useIsReviewer();
  const profileQuery = useProfile(candidateId);
  // Runs **de ce candidat** uniquement : un périmètre multi-candidats ne doit pas cocher l'étape
  // « analyse » parce qu'un autre candidat a déjà tourné (OPP-177).
  const runs = useRuns(1, candidateId);

  // On attend que chaque signal soit **résolu** (succès ou erreur) avant de décider quoi que ce
  // soit : sinon l'encart apparaîtrait puis disparaîtrait (flash) au fil des réponses réseau.
  if (!isReviewer || profileQuery.isPending || !stats || runs.isPending) return null;

  // Un profil absent (404 : candidat sans CV encore) est l'état « nouveau profil » par
  // excellence — on le traite comme un profil vide et on affiche le guide, au lieu de le masquer.
  const profile = profileQuery.data;

  const steps: Step[] = [
    {
      title: "Ajouter votre CV",
      description:
        "Importez un CV PDF : Opportune en extrait vos compétences et votre parcours.",
      // `experiences` peut manquer sur un profil mis en cache avant OPP-176 → fallback défensif.
      done: (profile?.experiences?.length ?? 0) > 0 || (profile?.skills.length ?? 0) > 0,
      action: { label: "Ajouter mon CV", to: "/profil" },
    },
    {
      title: "Récupérer de nouvelles offres",
      description: "Lancez une collecte pour alimenter votre catalogue d'offres.",
      done: stats.offres_total > 0,
      action: { label: "Récupérer des offres", to: "/offres" },
    },
    {
      title: "Lancer une analyse",
      description:
        "Opportune score les offres pour votre profil et recommande les meilleures.",
      // Runs du candidat ciblé (cf. `useRuns(1, candidateId)`). Erreur réseau → `data` absent →
      // étape non cochée : on propose l'action plutôt que de la masquer à tort.
      done: (runs.data?.total ?? 0) > 0,
      action: { label: "Lancer l'analyse", onClick: () => scrollToId("nouvelle-analyse") },
    },
  ];

  // Boucle de démarrage complète → plus besoin du guide.
  if (steps.every((s) => s.done)) return null;

  // Première étape non faite : mise en avant (« à faire maintenant »).
  const currentIndex = steps.findIndex((s) => !s.done);

  return (
    <section
      aria-label="Nouveau profil"
      className="space-y-3 rounded-lg border border-indigo-200 bg-indigo-50/60 p-4"
    >
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-indigo-700">
          Nouveau profil
        </h3>
        <p className="text-sm text-slate-600">Trois étapes pour lancer votre recherche.</p>
      </div>
      <ol className="space-y-2">
        {steps.map((step, i) => (
          <li
            key={i}
            className={`flex items-start gap-3 rounded-md border p-3 ${
              !step.done && i === currentIndex
                ? "border-indigo-300 bg-white"
                : "border-transparent bg-white/50"
            }`}
          >
            <span
              aria-hidden="true"
              className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white ${
                step.done ? "bg-emerald-600" : "bg-indigo-600"
              }`}
            >
              {step.done ? "✓" : i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p
                className={`text-sm font-medium ${
                  step.done ? "text-slate-400 line-through" : "text-slate-800"
                }`}
              >
                {step.title}
              </p>
              {!step.done && <p className="text-sm text-slate-600">{step.description}</p>}
            </div>
            {!step.done &&
              ("to" in step.action ? (
                <Link
                  to={step.action.to}
                  className="shrink-0 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
                >
                  {step.action.label}
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={step.action.onClick}
                  className="shrink-0 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
                >
                  {step.action.label}
                </button>
              ))}
          </li>
        ))}
      </ol>
    </section>
  );
}
