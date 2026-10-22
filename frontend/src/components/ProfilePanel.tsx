import { useEffect, useState, type ChangeEvent } from "react";
import { useProfile, useUpdateProfileSkills, useUploadCv } from "../api/profile";
import { useIsReviewer } from "../auth/roles";
import { ProfileExperiences } from "./ProfileExperiences";
import { ErrorNotice, Loading } from "./States";

/** Lit un fichier en base64 (sans le préfixe `data:…`), pour l'envoyer dans le corps JSON.
 * Via `FileReader` : disponible dans tout navigateur (et sous jsdom en test). */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("lecture du fichier impossible"));
    reader.onload = () => {
      const result = String(reader.result);
      const comma = result.indexOf(","); // "data:application/pdf;base64,XXXX"
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.readAsDataURL(file);
  });
}

/** Taille max d'un CV accepté côté front (10 Mo) : le PDF voyage encodé base64 dans un corps
 * JSON (~+33 %), on borne donc avant d'encoder pour ne pas gonfler mémoire et requête. */
const MAX_CV_BYTES = 10 * 1024 * 1024;

/**
 * Panneau « Mon profil » du cockpit (OPP-158) : consulte les compétences du candidat et, pour un
 * reviewer, les édite. Le scoring sous-estimait l'adéquation quand une compétence réellement
 * maîtrisée manquait des `skills` (ex. HTML/CSS, Agile, Scrum) ; combler ce trou de données ici
 * fiabilise le match. L'édition remplace la liste complète (`PUT /candidates/{id}/profile`) ;
 * au succès, le catalogue est invalidé → les scores se rafraîchissent sans rechargement.
 *
 * Affiche aussi le **parcours** extrait du CV (OPP-176, lecture seule) : jusqu'ici l'import CV
 * peuplait les expériences en base sans que rien n'apparaisse à l'écran. Quand le profil est
 * vide, une orientation invite à importer un CV plutôt que de laisser un panneau muet.
 */
export function ProfilePanel({ candidateId }: { candidateId: string }) {
  const isReviewer = useIsReviewer();
  const { data, isPending, isError, error } = useProfile(candidateId);
  const update = useUpdateProfileSkills();
  const upload = useUploadCv();
  // Copie éditable locale des compétences, resynchronisée quand la liste **serveur** change.
  const [skills, setSkills] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  // Erreur locale de l'import CV, en amont de la mutation (fichier trop gros ou illisible) :
  // la mutation ne part pas, donc `upload.error` ne la couvrirait pas.
  const [cvError, setCvError] = useState<Error | null>(null);

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

  const onCvSelected = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // réautorise la re-sélection du même fichier
    if (!file) return;
    setCvError(null);
    if (file.size > MAX_CV_BYTES) {
      setCvError(new Error("CV trop volumineux (10 Mo maximum)."));
      return;
    }
    let pdfBase64: string;
    try {
      pdfBase64 = await fileToBase64(file);
    } catch (err) {
      // Échec de lecture (fichier verrouillé/illisible) : on le signale au lieu d'un rejet muet.
      setCvError(err instanceof Error ? err : new Error("Lecture du fichier impossible."));
      return;
    }
    // Le contrat vient du profil existant : un CV ne le porte pas, le back l'exige.
    upload.mutate({ candidateId, pdfBase64, contractType: data.contract_type ?? "" });
  };

  const dirty = JSON.stringify(skills) !== JSON.stringify(data.skills);
  const canSave = dirty && skills.length > 0 && !update.isPending;

  // Fallback défensif : un profil mis en cache avant OPP-176 peut ne pas porter `experiences`.
  const experiences = data.experiences ?? [];
  // Profil « vierge » : ni compétences ni parcours. On oriente vers l'import CV au lieu d'afficher
  // un panneau muet. On se base sur les skills **serveur** (pas l'édition locale en cours).
  const isEmptyProfile = data.skills.length === 0 && experiences.length === 0;

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Mon profil
        </h3>
        <span className="text-xs text-slate-400">
          {data.name}
          {data.contract_type ? ` · ${data.contract_type}` : ""}
        </span>
      </div>

      {isEmptyProfile && (
        <p className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-3 text-sm text-slate-600">
          Ton profil est encore vide.{" "}
          {isReviewer
            ? "Importe ton CV (PDF) ci-dessous pour reconstituer automatiquement tes compétences et ton parcours."
            : "Un reviewer peut importer un CV pour le reconstituer."}
        </p>
      )}

      <section className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Compétences
        </h4>
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
      </section>

      <ProfileExperiences experiences={experiences} />

      {isReviewer && (
        <section className="space-y-1 border-t border-slate-100 pt-3">
          <label className="block text-sm font-medium text-slate-700">
            Importer un CV (PDF)
            <input
              type="file"
              accept="application/pdf"
              onChange={onCvSelected}
              disabled={upload.isPending}
              aria-label="Importer un CV PDF"
              className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border file:border-slate-300 file:bg-slate-50 file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-slate-100 disabled:opacity-50"
            />
          </label>
          <p className="text-xs text-slate-400">
            Le CV est analysé localement pour reconstituer ton profil et ton parcours. Les
            compétences corrigées à la main sont préservées.
          </p>
          {upload.isPending && (
            // L'analyse est un appel LLM **local synchrone** qui peut durer plusieurs minutes :
            // on l'annonce explicitement (avec un indicateur animé) pour que l'attente ne passe
            // pas pour un gel de l'interface.
            <div role="status" className="flex items-center gap-2 text-sm text-slate-600">
              <span
                aria-hidden="true"
                className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600"
              />
              <span>Analyse du CV en cours — l'extraction locale prend 1 à 5 minutes.</span>
            </div>
          )}
          {upload.isSuccess && (
            <span className="text-sm text-emerald-700">Profil mis à jour depuis le CV.</span>
          )}
          {cvError && <ErrorNotice error={cvError} />}
          {upload.isError && <ErrorNotice error={upload.error} />}
        </section>
      )}
    </div>
  );
}
