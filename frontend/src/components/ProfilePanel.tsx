import { useEffect, useState } from "react";
import { useProfile, useUpdateProfileSkills } from "../api/profile";
import { useIsReviewer } from "../auth/roles";
import { ErrorNotice, Loading } from "./States";

/**
 * Panneau « Mon profil » du cockpit (OPP-158) : consulte les compétences du candidat et, pour un
 * reviewer, les édite. Le scoring sous-estimait l'adéquation quand une compétence réellement
 * maîtrisée manquait des `skills` (ex. HTML/CSS, Agile, Scrum) ; combler ce trou de données ici
 * fiabilise le match. L'édition remplace la liste complète (`PUT /candidates/{id}/profile`) ;
 * au succès, le catalogue est invalidé → les scores se rafraîchissent sans rechargement.
 */
export function ProfilePanel({ candidateId }: { candidateId: string }) {
  const isReviewer = useIsReviewer();
  const { data, isPending, isError, error } = useProfile(candidateId);
  const update = useUpdateProfileSkills();
  // Copie éditable locale des compétences, resynchronisée quand la liste **serveur** change.
  const [skills, setSkills] = useState<string[]>([]);
  const [draft, setDraft] = useState("");

  // On ne resynchronise que lorsque les skills du serveur changent réellement (clé par valeur),
  // pas à chaque nouvelle référence de `data` : un refetch au focus, ou la modification d'un autre
  // champ du profil, ne doit pas écraser une édition de compétences en cours.
  const serverSkillsKey = data ? JSON.stringify(data.skills) : null;
  useEffect(() => {
    if (serverSkillsKey !== null) setSkills(JSON.parse(serverSkillsKey) as string[]);
  }, [serverSkillsKey]);

  if (candidateId === "") return null;
  if (isPending) return <Loading label="Chargement du profil…" />;
  // 404 (candidat sans profil) ou autre erreur : on le dit sobrement, sans bloquer le cockpit.
  if (isError) return <ErrorNotice error={error} />;
  if (!data) return null;

  const addSkill = () => {
    const value = draft.trim();
    if (value && !skills.some((s) => s.toLowerCase() === value.toLowerCase())) {
      setSkills([...skills, value]);
    }
    setDraft("");
  };
  const removeSkill = (skill: string) => setSkills(skills.filter((s) => s !== skill));

  const dirty = JSON.stringify(skills) !== JSON.stringify(data.skills);
  const canSave = dirty && skills.length > 0 && !update.isPending;

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Mon profil — compétences
        </h3>
        <span className="text-xs text-slate-400">
          {data.name}
          {data.contract_type ? ` · ${data.contract_type}` : ""}
        </span>
      </div>

      {skills.length === 0 ? (
        <p className="text-sm text-slate-500">Aucune compétence déclarée.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {skills.map((skill) => (
            <li
              key={skill}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700"
            >
              {skill}
              {isReviewer && (
                <button
                  type="button"
                  onClick={() => removeSkill(skill)}
                  aria-label={`Retirer ${skill}`}
                  className="text-slate-400 hover:text-rose-600"
                >
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {isReviewer && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addSkill();
                }
              }}
              placeholder="Ajouter une compétence (ex. HTML, Agile)…"
              aria-label="Ajouter une compétence"
              className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
            <button
              type="button"
              onClick={addSkill}
              disabled={draft.trim() === ""}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Ajouter
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => update.mutate({ candidateId, skills })}
              disabled={!canSave}
              className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50"
            >
              {update.isPending ? "Enregistrement…" : "Enregistrer les compétences"}
            </button>
            {update.isSuccess && !dirty && (
              <span className="text-sm text-emerald-700">Compétences à jour.</span>
            )}
            {update.isError && <ErrorNotice error={update.error} />}
          </div>
        </>
      )}
    </div>
  );
}
