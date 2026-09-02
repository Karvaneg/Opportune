// Persistance des versions de documents sur disque, sous forme de collection JSON
// (tableau). Les versions sont immuables : on ajoute, on ne modifie jamais une
// version déjà écrite (conservation — cf. OPP-045).
const fs = require("node:fs");
const path = require("node:path");

// Emplacement par défaut de la collection (dossier data/ ignoré par git).
const DEFAULT_PATH = path.join("data", "document-versions.json");

// Recharge toutes les versions ; retourne [] si le fichier n'existe pas.
function loadDocumentVersions(filePath = DEFAULT_PATH) {
  if (!fs.existsSync(filePath)) return [];
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

// Ajoute une version à la collection (remplacement défensif si l'id existe déjà,
// mais une version n'est en principe jamais réécrite). Retourne la version.
function saveDocumentVersion(documentVersion, filePath = DEFAULT_PATH) {
  const versions = loadDocumentVersions(filePath);
  const index = versions.findIndex((v) => v.id === documentVersion.id);

  if (index >= 0) versions[index] = documentVersion;
  else versions.push(documentVersion);

  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(versions, null, 2));
  return documentVersion;
}

// Réécrit la collection entière (utile pour les mises à jour groupées / tests).
function saveDocumentVersions(versions, filePath = DEFAULT_PATH) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(versions, null, 2));
  return versions;
}

module.exports = {
  DEFAULT_PATH,
  loadDocumentVersions,
  saveDocumentVersion,
  saveDocumentVersions,
};
