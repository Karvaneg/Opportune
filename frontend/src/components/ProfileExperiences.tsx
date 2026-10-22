import type { Experience } from "../api/types";

/**
 * Affiche le parcours extrait du CV (OPP-176), en lecture seule : une carte par expérience,
 * dans l'ordre renvoyé par le back. Chaque carte porte poste · entreprise · période (· lieu),
 * les réalisations en liste, et les compétences associées en puces. Les highlights peuvent être
 * longs : la mise en page les laisse s'écouler sans casser (pas de troncature).
 *
 * Rendu seulement s'il y a au moins une expérience : l'appelant gère l'état vide (orientation
 * vers l'import CV), car il connaît aussi l'état des compétences.
 */
export function ProfileExperiences({ experiences }: { experiences: Experience[] }) {
  if (experiences.length === 0) return null;

  return (
    <section className="space-y-3" aria-label="Parcours">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Parcours</h3>
      <ol className="space-y-3">
        {experiences.map((exp, i) => (
          // Index en clé : le parcours est une liste ordonnée en lecture seule, sans identifiant
          // stable ni réordonnancement — l'index reflète fidèlement la position.
          <li
            key={i}
            className="rounded-lg border border-slate-200 bg-slate-50/60 p-3"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
              <p className="font-medium text-slate-800">{exp.title}</p>
              <p className="text-xs text-slate-500">{exp.period}</p>
            </div>
            <p className="text-sm text-slate-600">
              {exp.company}
              {exp.location ? ` · ${exp.location}` : ""}
            </p>
            {exp.highlights.length > 0 && (
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                {exp.highlights.map((h, j) => (
                  <li key={j}>{h}</li>
                ))}
              </ul>
            )}
            {exp.skills && exp.skills.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {/* Clé par index : le back ne dédoublonne pas les skills d'une expérience, la
                    valeur ne garantit donc pas l'unicité. Liste statique et ordonnée. */}
                {exp.skills.map((s, k) => (
                  <li
                    key={k}
                    className="rounded-full bg-white px-2 py-0.5 text-xs text-slate-600 ring-1 ring-slate-200"
                  >
                    {s}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
