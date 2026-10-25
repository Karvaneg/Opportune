// Gestion des variables secrètes (OPP-074). Fournit un accès contrôlé aux
// secrets de l'application (tokens Notion/Discord, clés des connecteurs…) :
// chargement depuis un fichier .env local (gitignoré), lecture avec exigence de
// présence, et masquage pour tout affichage. Zéro dépendance (pas de dotenv).
//
// Règles de sécurité : les secrets vivent dans l'environnement / .env.local
// (jamais commité) ; ce module ne journalise jamais une valeur et expose
// maskSecret pour un affichage sûr.
const fs = require("node:fs");
const { ConfigError } = require("../errors");

// Parse le contenu d'un fichier .env en objet { CLE: valeur }. Ignore les
// lignes vides et les commentaires (#), retire les guillemets entourant la valeur.
function parseEnv(content = "") {
  const env = {};
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (line === "" || line.startsWith("#")) continue;

    const eq = line.indexOf("=");
    if (eq === -1) continue;

    const key = line.slice(0, eq).trim();
    if (!key) continue;

    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

// Charge un fichier .env dans une source (process.env par défaut). N'écrase pas
// les valeurs déjà définies, sauf si override=true. Retourne les paires lues
// (objet vide si le fichier n'existe pas).
function loadEnv(filePath, options = {}) {
  const { source = process.env, override = false } = options;
  if (!filePath || !fs.existsSync(filePath)) return {};

  const parsed = parseEnv(fs.readFileSync(filePath, "utf8"));
  for (const [key, value] of Object.entries(parsed)) {
    if (override || source[key] === undefined) source[key] = value;
  }
  return parsed;
}

// Vrai si le secret est défini et non vide dans la source.
function hasSecret(name, source = process.env) {
  const value = source[name];
  return value !== undefined && value !== "";
}

// Lit un secret. Par défaut requis : lève une erreur explicite s'il est absent
// ou vide. Avec required=false, retourne null quand il manque.
function getSecret(name, options = {}) {
  const { source = process.env, required = true } = options;
  if (!hasSecret(name, source)) {
    if (required) throw new ConfigError(`Variable secrète manquante : ${name}`, { name });
    return null;
  }
  return source[name];
}

// Vérifie la présence d'un ensemble de secrets ; lève en listant tous les
// manquants d'un coup (utile au démarrage de l'application).
function requireSecrets(names = [], source = process.env) {
  const missing = names.filter((name) => !hasSecret(name, source));
  if (missing.length > 0) {
    throw new ConfigError(`Variables secrètes manquantes : ${missing.join(", ")}`, { missing });
  }
  return true;
}

// Masque une valeur secrète pour l'affichage/les logs : ne révèle jamais le
// contenu, indique seulement si le secret est défini.
function maskSecret(value) {
  return value ? "••••••••" : "(non défini)";
}

module.exports = {
  parseEnv,
  loadEnv,
  hasSecret,
  getSecret,
  requireSecrets,
  maskSecret,
};
