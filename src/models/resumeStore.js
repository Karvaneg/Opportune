// Persistance des CV sur disque, sous forme de collection JSON (tableau).
const fs = require("node:fs");
const path = require("node:path");

// Emplacement par défaut de la collection (dossier data/ ignoré par git).
const DEFAULT_PATH = path.join("data", "resumes.json");

// Recharge tous les CV ; retourne [] si le fichier n'existe pas.
function loadResumes(filePath = DEFAULT_PATH) {
  if (!fs.existsSync(filePath)) return [];
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

// Réécrit toute la collection (utilisé quand plusieurs CV changent d'un coup,
// ex. bascule du CV par défaut). Retourne la collection écrite.
function saveResumes(resumes, filePath = DEFAULT_PATH) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(resumes, null, 2));
  return resumes;
}

// Sauvegarde un CV : le remplace si son id existe déjà, sinon l'ajoute.
// Retourne le CV enregistré.
function saveResume(resume, filePath = DEFAULT_PATH) {
  const resumes = loadResumes(filePath);
  const index = resumes.findIndex((r) => r.id === resume.id);

  if (index >= 0) resumes[index] = resume;
  else resumes.push(resume);

  saveResumes(resumes, filePath);
  return resume;
}

module.exports = { DEFAULT_PATH, loadResumes, saveResumes, saveResume };
