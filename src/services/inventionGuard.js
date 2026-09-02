// Vérification anti-invention (OPP-044). Critère du ticket : aucun diplôme,
// projet ou outil absent du profil ne doit être ajouté à une candidature.
//
// Garde-fou déterministe (sans LLM), en défense en profondeur des générateurs
// fidèles (resumeAdapter, coverLetterGenerator) et filet pour un contenu édité
// à la main. Portée de la vérification automatique :
//   - OUTILS / compétences : détectés via le lexique partagé et confrontés au profil ;
//   - PROJETS / expériences : le CV adapté ne doit contenir que des expériences du profil ;
// Les DIPLÔMES ne sont pas vérifiables de façon déterministe tant que le profil
// ne porte pas de formation structurée — hors portée ici (à traiter ultérieurement,
// les générateurs actuels n'en ajoutent de toute façon aucun).
const { canonicalizeSkillName, findSkillsInText } = require("./skillLexicon");
const { collectProfileSkills } = require("./resumeAdapter");

// Ensemble des compétences du profil sous forme canonique (pour comparaison).
function profileCanonicalSkills(profile) {
  const names = collectProfileSkills(profile)
    .map((skill) => canonicalizeSkillName(skill.name))
    .filter(Boolean);
  return new Set(names);
}

// Représentation stable d'une expérience (chaîne ou objet) pour comparaison.
function serializeExperience(experience) {
  return typeof experience === "string" ? experience : JSON.stringify(experience ?? "");
}

// Compétences/outils du lexique présents dans un texte mais absents du profil.
// Utilitaire général : utile pour contrôler un contenu saisi ou édité à la main.
// NB : un texte libre peut citer un outil au titre de l'entreprise/l'offre
// (ex. « chez Vercel ») — préférer les vérifications structurées ci-dessous pour
// les artefacts générés.
function findUnsupportedSkills(text, profile) {
  const owned = profileCanonicalSkills(profile);
  return findSkillsInText(typeof text === "string" ? text : "").filter((skill) => !owned.has(skill));
}

// Vérifie un texte libre : { ok, unsupportedSkills }.
function verifyText(text, profile) {
  const unsupportedSkills = findUnsupportedSkills(text, profile);
  return { ok: unsupportedSkills.length === 0, unsupportedSkills };
}

// Vérifie un CV adapté (resumeAdapter) : ses compétences et expériences doivent
// toutes provenir du profil. Une compétence est supportée si son libellé OU son
// nom canonique est détenu par le profil. Retourne le détail des éléments non
// supportés (idéalement vides — les générateurs sont fidèles par construction).
function verifyAdaptedResume(adaptedResume = {}, profile = {}) {
  const ownedCanonical = profileCanonicalSkills(profile);
  const ownedLabels = new Set(collectProfileSkills(profile).map((skill) => skill.name.toLowerCase()));

  const unsupportedSkills = (adaptedResume.skills ?? [])
    .filter((skill) => {
      const label = String(skill.name ?? "").toLowerCase();
      const canonical = canonicalizeSkillName(skill.name);
      return !ownedLabels.has(label) && !(canonical && ownedCanonical.has(canonical));
    })
    .map((skill) => skill.name);

  const ownedExperiences = new Set((profile.experiences ?? []).map(serializeExperience));
  const unsupportedExperiences = (adaptedResume.experiences ?? []).filter(
    (experience) => !ownedExperiences.has(serializeExperience(experience)),
  );

  return {
    ok: unsupportedSkills.length === 0 && unsupportedExperiences.length === 0,
    unsupportedSkills,
    unsupportedExperiences,
  };
}

// Vérifie une lettre de motivation : les compétences mises en avant doivent être
// détenues par le profil. On contrôle les revendications de compétences
// (highlightedSkills) plutôt que le texte entier, pour ne pas confondre une
// mention de l'entreprise/l'offre avec une compétence revendiquée.
function verifyCoverLetter(letter = {}, profile = {}) {
  const ownedCanonical = profileCanonicalSkills(profile);
  const ownedLabels = new Set(collectProfileSkills(profile).map((skill) => skill.name.toLowerCase()));

  const unsupportedSkills = (letter.highlightedSkills ?? []).filter((name) => {
    const canonical = canonicalizeSkillName(name);
    return !ownedLabels.has(String(name).toLowerCase()) && !(canonical && ownedCanonical.has(canonical));
  });

  return { ok: unsupportedSkills.length === 0, unsupportedSkills };
}

// Vérifie une candidature complète (CV adapté + lettre). Retourne un rapport
// agrégé { ok, resume, letter } : socle du blocage d'envoi tant que ce n'est pas
// validé (cf. OPP-053).
function verifyApplication({ adaptedResume, coverLetter } = {}, profile = {}) {
  const resume = adaptedResume ? verifyAdaptedResume(adaptedResume, profile) : null;
  const letter = coverLetter ? verifyCoverLetter(coverLetter, profile) : null;
  return {
    ok: (resume?.ok ?? true) && (letter?.ok ?? true),
    resume,
    letter,
  };
}

module.exports = {
  findUnsupportedSkills,
  verifyText,
  verifyAdaptedResume,
  verifyCoverLetter,
  verifyApplication,
};
