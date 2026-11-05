/** Décode du base64 (sans préfixe `data:…`) en octets. Pendant de `fileToBase64` : l'export de
 * données (OPP-232) arrive en base64 dans le JSON de l'API. */
export function base64ToBytes(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}
