/** Taille en octets → texte court en français : « 2,8 Go », « 512 Mo ». */
export function formatBytes(bytes: number): string {
  const GIGABYTE = 1024 ** 3;
  const MEGABYTE = 1024 ** 2;
  if (bytes >= GIGABYTE) {
    return `${(bytes / GIGABYTE).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Go`;
  }
  return `${Math.max(1, Math.round(bytes / MEGABYTE)).toLocaleString("fr-FR")} Mo`;
}
