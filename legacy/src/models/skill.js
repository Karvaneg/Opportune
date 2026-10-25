// Modèle d'une compétence structurée : nom, catégorie, niveau, expérience.
// Rattachée au profil via profile.structuredSkills (cf. skillService).
// La validation vit dans src/services/skillService.js.

// Niveaux de maîtrise reconnus (échelle fermée).
const SKILL_LEVELS = ["notion", "intermédiaire", "avancé", "expert"];

// Construit une compétence à partir de données partielles.
// category reste libre ; level par défaut « notion » ; experienceYears optionnel.
function createSkill(data = {}) {
  return {
    name: data.name ?? "", // obligatoire
    category: data.category ?? null, // libre
    level: data.level ?? "notion",
    experienceYears: data.experienceYears ?? undefined, // nombre >= 0 si fourni
  };
}

// Retourne une copie de la compétence avec les modifications appliquées (immutable).
function updateSkill(skill, changes = {}) {
  return { ...skill, ...changes };
}

module.exports = { SKILL_LEVELS, createSkill, updateSkill };
