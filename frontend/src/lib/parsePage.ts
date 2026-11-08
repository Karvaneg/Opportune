/**
 * Lit `?page=` : suite de chiffres valant au moins 1, sinon page 1. La vérification stricte
 * écarte `1e21` ou `2.0`, que `Number` accepte mais que le back refuserait (400).
 */
export function parsePage(raw: string | null): number {
  if (raw === null || !/^\d+$/.test(raw)) return 1;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n >= 1 ? n : 1;
}
