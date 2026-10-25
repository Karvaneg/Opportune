// Persistance des candidatures sur disque, sous forme de collection JSON (tableau).
const fs = require("node:fs");
const path = require("node:path");

// Emplacement par défaut de la collection (dossier data/ ignoré par git).
const DEFAULT_PATH = path.join("data", "applications.json");

// Recharge toutes les candidatures ; retourne [] si le fichier n'existe pas.
function loadApplications(filePath = DEFAULT_PATH) {
  if (!fs.existsSync(filePath)) return [];
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

// Sauvegarde une candidature : la remplace si son id existe déjà, sinon l'ajoute.
// Retourne la candidature enregistrée.
function saveApplication(application, filePath = DEFAULT_PATH) {
  const applications = loadApplications(filePath);
  const index = applications.findIndex((a) => a.id === application.id);

  if (index >= 0) applications[index] = application;
  else applications.push(application);

  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(applications, null, 2));
  return application;
}

// Réécrit la collection entière (utile pour les mises à jour groupées).
function saveApplications(applications, filePath = DEFAULT_PATH) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(applications, null, 2));
  return applications;
}

module.exports = { DEFAULT_PATH, loadApplications, saveApplication, saveApplications };
