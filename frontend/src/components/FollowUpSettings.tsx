import { useState } from "react";
import {
  useFollowUpSettings,
  useSaveFollowUpSettings,
  type FollowUpSettings as Delays,
} from "../api/followUps";
import { useIsReviewer } from "../auth/roles";
import { ErrorNotice, Hint, Loading } from "./States";

/**
 * Réglage des délais de relance (OPP-235) : jours après une candidature, et après un entretien,
 * saisis séparés par des virgules. Le back valide (entiers de 1 à 365, croissants) et renvoie ce
 * qu'il a enregistré, que l'on réaffiche.
 */
export function FollowUpSettings() {
  const isReviewer = useIsReviewer();
  const { data, isPending, isError, error } = useFollowUpSettings();
  // La mutation vit ici pour survivre au remontage du formulaire (message « enregistré » gardé).
  const save = useSaveFollowUpSettings();

  if (!isReviewer) {
    return <Hint>Un reviewer peut régler les délais de relance.</Hint>;
  }
  if (isPending) return <Loading label="Chargement des réglages…" />;
  if (isError) return <ErrorNotice error={error} />;

  // La clé remonte le formulaire quand les délais enregistrés changent (refetch après un import,
  // par exemple) : les champs repartent des valeurs à jour au lieu de les écraser à l'enregistrement.
  const key = `${data.after_application.join(",")}|${data.after_interview.join(",")}`;
  return <FollowUpForm key={key} initial={data} save={save} />;
}

/**
 * Liste de jours saisie (« 5, 8 ») → nombres ; `null` si un élément n'est pas un entier.
 * Un champ vide donne une liste vide (aucune relance pour ce cas).
 */
export function parseDays(text: string): number[] | null {
  const parts = text
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");
  if (parts.some((part) => !/^\d+$/.test(part))) return null;
  return parts.map(Number);
}

function FollowUpForm({
  initial,
  save,
}: {
  initial: Delays;
  save: ReturnType<typeof useSaveFollowUpSettings>;
}) {
  const [afterApplication, setAfterApplication] = useState(initial.after_application.join(", "));
  const [afterInterview, setAfterInterview] = useState(initial.after_interview.join(", "));

  const applicationDays = parseDays(afterApplication);
  const interviewDays = parseDays(afterInterview);
  const invalid = applicationDays === null || interviewDays === null;

  const resetMessage = () => {
    if (save.isSuccess || save.isError) save.reset();
  };

  const submit = () => {
    if (applicationDays === null || interviewDays === null) return;
    save.mutate(
      { after_application: applicationDays, after_interview: interviewDays },
      {
        onSuccess: (saved: Delays) => {
          setAfterApplication(saved.after_application.join(", "));
          setAfterInterview(saved.after_interview.join(", "));
        },
      },
    );
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface-raised p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Rappels de relance
      </h3>
      <p className="text-sm text-ink-muted">
        Une candidature apparaît dans « À relancer » sur l'Accueil quand une relance est due. Chaque
        jour réglé correspond à une relance, compté depuis la candidature ou depuis le dernier
        entretien passé. Dès que tu notes une relance, la suivante est proposée le dernier de ces
        délais plus tard ; quand toutes les relances prévues sont notées, plus de rappel. Sépare les jours
        par des virgules ; laisse un champ vide pour ne pas être relancé.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm font-medium text-ink">
          Après une candidature (jours)
          <input
            type="text"
            inputMode="numeric"
            value={afterApplication}
            onChange={(e) => {
              setAfterApplication(e.target.value);
              resetMessage();
            }}
            placeholder="5, 8"
            className="mt-1 block w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink"
          />
        </label>
        <label className="block text-sm font-medium text-ink">
          Après un entretien (jours)
          <input
            type="text"
            inputMode="numeric"
            value={afterInterview}
            onChange={(e) => {
              setAfterInterview(e.target.value);
              resetMessage();
            }}
            placeholder="5, 8, 15"
            className="mt-1 block w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink"
          />
        </label>
      </div>
      {invalid && (
        <p className="text-sm text-danger">
          Saisis des nombres entiers de jours, séparés par des virgules.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={invalid || save.isPending}
          className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
        >
          {save.isPending ? "Enregistrement…" : "Enregistrer les délais"}
        </button>
        {save.isSuccess && (
          <span className="text-sm text-success-text">Délais de relance enregistrés.</span>
        )}
        {save.isError && <ErrorNotice error={save.error} />}
      </div>
    </div>
  );
}
