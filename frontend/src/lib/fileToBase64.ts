/** Lit un fichier en base64 (sans le préfixe `data:…`), pour l'envoyer dans le corps JSON.
 * Via `FileReader` : disponible dans tout navigateur (et sous jsdom en test). Partagé par l'import
 * de CV (OPP-174) et l'import de données (OPP-232). */
export function fileToBase64(file: File): Promise<string> {
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
