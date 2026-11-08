import { useState } from "react";
import {
  useAtsSettings,
  useSaveAtsSettings,
  type AtsCompany,
  type AtsSettings as AtsData,
} from "../api/settings";
import { ErrorNotice, Loading } from "./States";

/**
 * Réglage des entreprises ciblées (OPP-226) : l'utilisateur colle l'URL de la page carrière de
 * chaque entreprise qu'il vise, une par ligne. Opportune en déduit l'ATS (Greenhouse ou Lever) et
 * l'identifiant de l'entreprise, puis la collecte « entreprises ciblées » lit leurs offres publiées
 * en France.
 *
 * Le back vérifie chaque nouvelle entreprise auprès de son ATS : une URL non reconnue ou une
 * entreprise introuvable refuse tout l'enregistrement, avec un message qui cite la ligne. Après
 * succès, le champ est resynchronisé sur les URLs canoniques retenues (doublons fusionnés), et
 * le nombre d'offres en France des entreprises qu'on vient d'ajouter est affiché.
 */
export function AtsSettings() {
  const { data, isPending, isError, error } = useAtsSettings();

  if (isPending) return <Loading label="Chargement des réglages…" />;
  if (isError) return <ErrorNotice error={error} />;

  return <AtsForm initialCompanies={data.companies} />;
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count > 1 ? "s" : ""}`;
}

function AtsForm({ initialCompanies }: { initialCompanies: AtsCompany[] }) {
  const save = useSaveAtsSettings();
  const [text, setText] = useState(initialCompanies.map((company) => company.url).join("\n"));

  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
  const configuredCount = initialCompanies.length;
  // Champ vide = tout supprimer, permis seulement s'il y a quelque chose à supprimer (RG-6).
  const removesAll = lines.length === 0 && configuredCount > 0;
  const canSave = (lines.length > 0 || removesAll) && !save.isPending;
  // Entreprises qui viennent d'être vérifiées : le back donne leur nombre d'offres en France.
  const checked = save.data?.companies.filter((company) => company.offers_in_france !== null) ?? [];

  const submit = () => {
    if (removesAll && !window.confirm("Supprimer toutes les entreprises ciblées ?")) return;
    save.mutate(
      { companies: lines },
      { onSuccess: (saved: AtsData) => setText(saved.companies.map((c) => c.url).join("\n")) },
    );
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface-raised p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
          Entreprises ciblées
        </h3>
        <span
          className={
            configuredCount > 0
              ? "rounded-full bg-success/15 px-3 py-1 text-xs font-medium text-success-text"
              : "rounded-full bg-ink/5 px-3 py-1 text-xs font-medium text-ink-muted"
          }
        >
          {configuredCount > 0 ? plural(configuredCount, "entreprise") : "Aucune entreprise"}
        </span>
      </div>

      <div className="space-y-2 text-sm text-ink-muted">
        <p>
          Colle l'adresse de la page carrière d'une entreprise par ligne. La collecte « entreprises
          ciblées » lit les offres qu'elle publie et garde celles situées en France. Pour supprimer
          toutes les entreprises, vide le champ puis enregistre.
        </p>
        <p>
          Pages reconnues : celles hébergées par Greenhouse{" "}
          (<code>job-boards.greenhouse.io/…</code> ou <code>boards.greenhouse.io/…</code>) ou par
          Lever (<code>jobs.lever.co/…</code>). Si le site carrière d'une entreprise affiche une
          autre adresse, elle n'utilise pas l'un de ces outils. 50 entreprises au maximum.
        </p>
      </div>

      <label className="block text-sm font-medium text-ink">
        Pages carrière (une par ligne)
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            // Le message du dernier enregistrement ne vaut plus pour une saisie modifiée.
            if (save.isSuccess || save.isError) save.reset();
          }}
          rows={5}
          spellCheck={false}
          placeholder="https://jobs.lever.co/entreprise"
          aria-label="Pages carrière des entreprises ciblées"
          className="mt-1 block w-full rounded-md border border-border bg-surface px-3 py-2 font-mono text-sm text-ink"
        />
      </label>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={submit}
          disabled={!canSave}
          className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
        >
          {save.isPending
            ? "Vérification…"
            : removesAll
              ? "Supprimer toutes les entreprises"
              : "Enregistrer les entreprises"}
        </button>
        {save.isSuccess && (
          <span className="text-sm text-success-text">
            {save.data.companies.length === 0
              ? "Entreprises ciblées supprimées."
              : "Entreprises ciblées enregistrées."}
          </span>
        )}
        {save.isError && <ErrorNotice error={save.error} />}
      </div>

      {save.isSuccess && checked.length > 0 && (
        <ul className="space-y-1 text-sm text-ink-muted" aria-label="Entreprises vérifiées">
          {checked.map((company) => (
            <li key={company.url}>
              <span className="font-mono">{company.slug}</span> :{" "}
              {plural(company.offers_in_france ?? 0, "offre")} en France actuellement
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
