import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { KeyRound } from "lucide-react";
import { useProfile } from "../api/profile";
import { useRuns } from "../api/runs";
import { useAdzunaSettings } from "../api/settings";
import { useLlmStatus } from "../api/system";
import { useIsReviewer } from "../auth/roles";
import type { CandidateStats } from "../api/types";

/** Fait défiler jusqu'à un ancrage de la page, en douceur. Pur confort de navigation (pas de
 * logique métier) : sous jsdom, `scrollIntoView` n'existe pas, d'où le garde optionnel. */
function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView?.({ behavior: "smooth", block: "start" });
}

/** Remonte en haut de page, là où vit le bandeau d'installation de l'assistant local
 * (`LlmBanner`, hors du `<main>`) : il n'a pas d'ancrage propre, on vise donc le sommet. Garde
 * optionnel car `scrollTo` n'existe pas sous jsdom. */
function scrollToTop() {
  window.scrollTo?.({ top: 0, behavior: "smooth" });
}

/** Une étape du guide : son libellé, son état, et l'action qui y mène — soit un lien vers une
 * autre page (`to`), soit un défilement intra-page (`onClick`). */
type StepAction = { label: string; to: string } | { label: string; onClick: () => void };
type Step = {
  title: string;
  description: string;
  done: boolean;
  action: StepAction;
};

/**
 * Guide d'accueil « Nouveau profil » (OPP-177, étendu en OPP-195) : transforme un cockpit vide
 * en chemin clair pour le premier lancement. Les étapes de la boucle de démarrage — préparer
 * l'assistant local, ajouter un CV, récupérer des offres, lancer une analyse — voient leur
 * avancement **déduit de l'état réel** (statut LLM, profil, pool d'offres, runs du candidat),
 * sans drapeau persistant. S'y ajoute une invite **optionnelle** à saisir les clés Adzuna pour de
 * vraies offres. Chaque étape à faire renvoie à l'action existante (navigation guidée, pas de
 * duplication d'UI).
 *
 * Le guide disparaît dès que la **boucle métier** (CV → offres → analyse) est complète : c'est
 * elle qui marque un démarrage « terminé ». L'état du LLM et des clés enrichit l'affichage mais
 * ne le pilote pas — une fois l'utilisateur lancé, le bandeau LLM suffit à signaler un modèle
 * manquant, et l'invite Adzuna vit sur la page Offres.
 *
 * Réservé au **reviewer** : les étapes (importer un CV, curer le pool d'offres, lancer une
 * analyse, saisir des secrets) sont des actions de curation qu'un simple lecteur ne peut mener.
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
  // Assistant local (OPP-195) : fail-open, comme `useLlmReady`. Statut en cours de chargement, en
  // erreur ou indéterminable (vieux backend sans la route) → on considère le modèle prêt, l'étape
  // se coche et ne parasite pas le guide. Le bandeau en haut reste la source de vérité visible.
  const llmStatus = useLlmStatus();
  const llmReady = !llmStatus.data || llmStatus.data.model_present;
  // Clés Adzuna (OPP-195) : invite optionnelle, affichée seulement une fois l'état résolu et
  // explicitement « non configuré » (pas de clignotement au chargement).
  const adzuna = useAdzunaSettings();
  const adzunaMissing = adzuna.data?.configured === false;

  // On attend que chaque signal **de la boucle métier** soit résolu (succès ou erreur) avant de
  // décider : sinon l'encart apparaîtrait puis disparaîtrait (flash) au fil des réponses réseau.
  // Le statut LLM et les clés, fail-open / optionnels, ne bloquent pas cette décision.
  if (!isReviewer || profileQuery.isPending || !stats || runs.isPending) return null;

  // Un profil absent (404 : candidat sans CV encore) est l'état « nouveau profil » par
  // excellence — on le traite comme un profil vide et on affiche le guide, au lieu de le masquer.
  const profile = profileQuery.data;

  // Étapes de la boucle de démarrage : leur complétion pilote l'affichage du guide.
  const coreSteps: Step[] = [
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

  // Boucle de démarrage complète → plus besoin du guide (l'état LLM/clés n'entre pas en compte).
  if (coreSteps.every((s) => s.done)) return null;

  // L'assistant local n'apparaît comme étape **que s'il n'est pas prêt** : une fois le modèle
  // installé, l'afficher coché et barré n'apprend rien et intrigue (c'est un prérequis technique,
  // pas une action du parcours). Quand il manque, il passe en tête — prérequis de la collecte et
  // de l'analyse (chacune fait un passage LLM) — et renvoie au bandeau d'installation en haut.
  const llmStep: Step = {
    title: "Préparer l'assistant local",
    description:
      "Opportune installe une seule fois un petit modèle d'IA local pour analyser les offres et rédiger vos lettres. L'installation se lance depuis le bandeau en haut.",
    done: false,
    action: { label: "Voir l'installation", onClick: scrollToTop },
  };
  const steps: Step[] = llmReady ? coreSteps : [llmStep, ...coreSteps];

  // Première étape non faite : mise en avant (« à faire maintenant »).
  const currentIndex = steps.findIndex((s) => !s.done);

  return (
    <section
      aria-label="Nouveau profil"
      className="space-y-3 rounded-lg border border-brand/30 bg-brand/5 p-4"
    >
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-brand">
          Nouveau profil
        </h3>
        <p className="text-sm text-ink-muted">Quelques étapes pour lancer votre recherche.</p>
      </div>
      <ol className="space-y-2">
        {steps.map((step, i) => (
          <StepRow
            key={i}
            marker={step.done ? "✓" : i + 1}
            title={step.title}
            description={step.description}
            done={step.done}
            highlight={!step.done && i === currentIndex}
            action={step.action}
          />
        ))}
      </ol>
      {/* Invite optionnelle (OPP-195) : saisir des clés Adzuna pour récupérer de vraies offres en
          ligne. Sans clés, l'app reste utile (espace Démo). Non comptée dans la complétion. */}
      {adzunaMissing && (
        <ol className="space-y-2">
          <StepRow
            marker={<KeyRound className="h-3.5 w-3.5" aria-hidden />}
            title="Ajouter vos clés Adzuna"
            description="Optionnel : pour récupérer de vraies offres en ligne. Sans clés, vous pouvez explorer l'espace Démo."
            done={false}
            highlight={false}
            optional
            action={{ label: "Ajouter les clés", to: "/reglages" }}
          />
        </ol>
      )}
    </section>
  );
}

/**
 * Une ligne du guide : pastille d'état, libellé + description, et l'action qui y mène (lien
 * d'autre page, ou défilement intra-page). Une étape faite perd son action et son intitulé est
 * barré ; une étape optionnelle porte une pastille neutre plutôt qu'un numéro.
 */
function StepRow({
  marker,
  title,
  description,
  done,
  highlight,
  action,
  optional = false,
}: {
  marker: ReactNode;
  title: string;
  description: string;
  done: boolean;
  highlight: boolean;
  action: StepAction;
  optional?: boolean;
}) {
  return (
    <li
      className={`flex items-start gap-3 rounded-md border p-3 ${
        highlight ? "border-brand/30 bg-surface-raised" : "border-transparent bg-surface-raised/50"
      }`}
    >
      <span
        aria-hidden="true"
        className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-on-brand ${
          done ? "bg-success" : optional ? "bg-ink-muted" : "bg-brand"
        }`}
      >
        {marker}
      </span>
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-medium ${done ? "text-ink-muted line-through" : "text-ink"}`}>
          {title}
        </p>
        {!done && <p className="text-sm text-ink-muted">{description}</p>}
      </div>
      {!done &&
        ("to" in action ? (
          <Link
            to={action.to}
            className="shrink-0 rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong"
          >
            {action.label}
          </Link>
        ) : (
          <button
            type="button"
            onClick={action.onClick}
            className="shrink-0 rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong"
          >
            {action.label}
          </button>
        ))}
    </li>
  );
}
