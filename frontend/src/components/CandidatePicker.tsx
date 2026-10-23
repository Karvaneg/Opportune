/**
 * Sélecteur de candidat partagé entre les pages du périmètre (cockpit, profil). Ne s'affiche
 * qu'au-delà d'un candidat : un périmètre mono-candidat n'a rien à choisir. Factorise un bloc
 * jusque-là dupliqué, pour un libellé `aria` propre à chaque page.
 */
export function CandidatePicker({
  candidates,
  value,
  onChange,
  ariaLabel,
}: {
  candidates: string[];
  value: string;
  onChange: (next: string) => void;
  ariaLabel: string;
}) {
  if (candidates.length <= 1) return null;
  return (
    <label className="flex items-center gap-2 text-sm text-slate-500">
      Candidat
      <select
        aria-label={ariaLabel}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
      >
        {candidates.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    </label>
  );
}
