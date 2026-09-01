// Persistance du profil candidat sur disque, au format JSON.
const fs = require("node:fs");
const path = require("node:path");

// Emplacement par défaut du profil (dossier data/ ignoré par git).
const DEFAULT_PATH = path.join("data", "profile.json");

// Sauvegarde le profil ; crée le dossier parent si besoin. Retourne le chemin écrit.
function saveProfile(profile, filePath = DEFAULT_PATH) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(profile, null, 2));
  return filePath;
}

// Recharge un profil depuis le disque ; retourne null si le fichier n'existe pas.
function loadProfile(filePath = DEFAULT_PATH) {
  if (!fs.existsSync(filePath)) return null;
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

module.exports = { DEFAULT_PATH, saveProfile, loadProfile };
