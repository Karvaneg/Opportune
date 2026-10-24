import { useState } from "react";
import { useCreateSearch, useRenameSearch } from "../api/searches";
import type { Search } from "../api/types";
import { useIsReviewer } from "../auth/roles";
import { useTargetCandidate } from "../auth/useTargetCandidate";
import { ErrorNotice } from "./States";

/** Libellé affichable d'une recherche : son nom, ou son id technique à défaut (enrôlée sans nom). */
function labelOf(search: Search): string {
  return search.label || search.id;
}

/**
 * Sélecteur global de recherche (OPP-184) — le cœur de l'UX « recherches multiples ». Une seule
 * barre, partagée par toutes les pages via `useTargetCandidate` : **basculer** d'une recherche à
 * l'autre, **créer** une recherche nommée, **renommer** l'active. La création / le renommage sont
 * réservés au rôle reviewer (modifier le périmètre) ; la bascule reste ouverte. Remplace les
 * sélecteurs par page, qui n'affichaient que l'id brut.
 */
export function SearchBar() {
  // `searches` ET `isPending` viennent de la **même** source (le contexte, un unique abonnement
  // à `GET /searches`) : sinon deux abonnements distincts à la même requête peuvent se
  // désynchroniser le temps d'un commit et faire clignoter l'état « Aucune recherche » (dont un
  // bouton transitoire aussitôt détaché). On ne rend donc rien tant que le périmètre n'est pas
  // résolu.
  const { searches, target, setCandidate, isPending, isError, error } = useTargetCandidate();
  const isReviewer = useIsReviewer();
  const create = useCreateSearch();
  const rename = useRenameSearch();
  // `idle` : sélecteur + actions ; `creating`/`renaming` : saisie du nom en ligne.
  const [mode, setMode] = useState<"idle" | "creating" | "renaming">("idle");
  const [draft, setDraft] = useState("");

  const active = searches.find((s) => s.id === target) ?? null;

  const openCreate = () => {
    setDraft("");
    setMode("creating");
  };
  const openRename = () => {
    setDraft(active ? labelOf(active) : "");
    setMode("renaming");
  };
  const cancel = () => {
    setMode("idle");
    setDraft("");
    create.reset();
    rename.reset();
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const label = draft.trim();
    if (!label) return;
    if (mode === "creating") {
      // Au succès on bascule sur la nouvelle recherche (son id généré) : la liste réinvalidée la
      // contient déjà, donc `target` s'y fixe au lieu de retomber sur la première.
      create.mutate(label, {
        onSuccess: (search) => {
          setCandidate(search.id);
          cancel();
        },
      });
    } else if (mode === "renaming" && active) {
      rename.mutate({ id: active.id, label }, { onSuccess: cancel });
    }
  };

  // Périmètre pas encore résolu : rien (évite le flash « Aucune recherche »).
  if (isPending) return null;

  // `GET /searches` a échoué : un périmètre « vide » n'est pas fiable (API HS) — on le signale
  // au lieu de laisser toute l'app paraître vide sans explication.
  if (isError) return <ErrorNotice error={error} />;

  // Périmètre vide : rien à basculer. Un reviewer peut amorcer une première recherche.
  if (searches.length === 0 && mode === "idle") {
    if (!isReviewer) return null;
    return (
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-500">Aucune recherche.</span>
        <button
          type="button"
          onClick={openCreate}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Nouvelle recherche
        </button>
      </div>
    );
  }

  const pending = create.isPending || rename.isPending;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        {mode === "idle" ? (
          <>
            <label className="flex items-center gap-2 text-sm text-slate-500">
              Recherche
              <select
                aria-label="Recherche active"
                value={target}
                onChange={(e) => setCandidate(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-900"
              >
                {searches.map((s) => (
                  <option key={s.id} value={s.id}>
                    {labelOf(s)}
                  </option>
                ))}
              </select>
            </label>
            {isReviewer && (
              <div className="flex items-center gap-1.5">
                {active && (
                  <button
                    type="button"
                    onClick={openRename}
                    className="rounded-md px-2 py-1.5 text-sm text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
                  >
                    Renommer
                  </button>
                )}
                <button
                  type="button"
                  onClick={openCreate}
                  className="rounded-md px-2 py-1.5 text-sm font-medium text-indigo-700 transition-colors hover:bg-indigo-50"
                >
                  Nouvelle recherche
                </button>
              </div>
            )}
          </>
        ) : (
          <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
            <input
              aria-label="Nom de la recherche"
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ex. Data Analyst Paris"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
            <button
              type="submit"
              disabled={pending || draft.trim() === ""}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {mode === "creating" ? "Créer" : "Enregistrer"}
            </button>
            <button
              type="button"
              onClick={cancel}
              className="rounded-md px-2 py-1.5 text-sm text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            >
              Annuler
            </button>
          </form>
        )}
      </div>
      {create.isError && <ErrorNotice error={create.error} />}
      {rename.isError && <ErrorNotice error={rename.error} />}
    </div>
  );
}
