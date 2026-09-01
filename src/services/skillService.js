// Structuration des compétences du candidat : validation, extraction simple
// depuis le texte d'un CV (extractedText) et rattachement au profil.
// Volontairement sans analyse automatique complexe (appariement par lexique).
const { SKILL_LEVELS, createSkill } = require("../models/skill");
const { updateProfile } = require("../models/userProfile");

// Vrai si la valeur est une chaîne non vide (espaces seuls exclus).
function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

// Échappe les métacaractères d'une expression régulière.
function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Vrai si la compétence apparaît comme un terme entier dans le texte (bornée par
// des caractères non alphanumériques). Gère « Java » vs « JavaScript », « Node.js »…
function containsSkill(haystackLower, nameLower) {
  const re = new RegExp(`(?<![a-z0-9])${escapeRegExp(nameLower)}(?![a-z0-9])`);
  return re.test(haystackLower);
}

// Déduplique une liste de compétences par nom, insensible à la casse.
// Conserve la première occurrence (donc le nom déjà présent).
function dedupeByName(skills) {
  const seen = new Set();
  const out = [];
  for (const skill of skills) {
    const key = String(skill.name).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(skill);
  }
  return out;
}

// Contrôle une compétence. Retourne { valid, errors }.
function validateSkill(skill) {
  const errors = [];

  if (!isNonEmptyString(skill.name)) {
    errors.push("Le nom de la compétence est obligatoire");
  }
  if (!SKILL_LEVELS.includes(skill.level)) {
    errors.push("Le niveau de compétence est invalide");
  }
  if (skill.experienceYears !== undefined && skill.experienceYears !== null) {
    const y = skill.experienceYears;
    if (typeof y !== "number" || Number.isNaN(y) || y < 0) {
      errors.push("L'expérience doit être un nombre positif ou nul");
    }
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

// Extrait des compétences depuis le texte d'un CV par appariement avec un
// lexique fourni (knownSkills : noms ou objets { name }). Insensible à la casse,
// termes entiers, dédupliqué. Conserve le nom tel qu'écrit dans le lexique.
// Ne persiste rien : renvoie simplement les compétences détectées (niveau « notion »).
function extractSkillsFromText(text, knownSkills = []) {
  if (!isNonEmptyString(text)) return [];

  const haystack = text.toLowerCase();
  const seen = new Set();
  const found = [];

  for (const known of knownSkills) {
    const name = typeof known === "string" ? known : known?.name;
    if (!isNonEmptyString(name)) continue;

    const key = name.toLowerCase();
    if (seen.has(key)) continue; // dédup insensible à la casse
    if (containsSkill(haystack, key)) {
      seen.add(key);
      found.push(createSkill({ name, level: "notion" }));
    }
  }

  return found;
}

// Rattache des compétences structurées au profil, dans profile.structuredSkills.
// mode est obligatoire et explicite : "replace" (remplace) ou "merge" (fusionne,
// en dédupliquant par nom). Valide chaque compétence. Retourne un nouveau profil
// (immutable) ; ne persiste pas — la sauvegarde reste explicite via profileStore.
function attachSkillsToProfile(profile, skills, options = {}) {
  const { mode } = options;
  if (mode !== "replace" && mode !== "merge") {
    throw new Error('attachSkillsToProfile : option mode requise ("replace" ou "merge")');
  }

  for (const skill of skills) {
    const validation = validateSkill(skill);
    if (!validation.valid) throw new Error(validation.errors.join(", "));
  }

  const next =
    mode === "replace"
      ? dedupeByName(skills)
      : dedupeByName([...(profile.structuredSkills ?? []), ...skills]);

  return updateProfile(profile, { structuredSkills: next });
}

module.exports = {
  validateSkill,
  extractSkillsFromText,
  attachSkillsToProfile,
};
