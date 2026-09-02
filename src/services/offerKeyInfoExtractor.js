// Extraction des informations clés d'une offre (OPP-030).
// À partir d'une offre normalisée (jobOffer), dérive les éléments utiles à
// l'analyse et au scoring offre↔profil : compétences, expérience, lieu, salaire,
// télétravail, langues, contraintes.
//
// Extraction heuristique et déterministe (aucune dépendance externe, aucun LLM,
// en continuité de la stack Node actuelle) : lit les champs structurés quand ils
// existent, sinon analyse le texte libre (titre + description + données brutes).
//
// Le vocabulaire des compétences est mutualisé dans skillLexicon (partagé avec
// la comparaison offre↔profil) ; l'appariement de termes vit dans textMatch.
const { containsTerm } = require("./textMatch");
const { findSkillsInText } = require("./skillLexicon");

// --- Catalogues de détection -------------------------------------------------

// Langues reconnues : nom canonique (français) + variantes multilingues.
const LANGUAGE_CATALOG = [
  { name: "français", aliases: ["français", "francais", "french"] },
  { name: "anglais", aliases: ["anglais", "english"] },
  { name: "allemand", aliases: ["allemand", "german", "deutsch"] },
  { name: "espagnol", aliases: ["espagnol", "spanish", "español"] },
  { name: "italien", aliases: ["italien", "italian"] },
];

// Villes reconnues pour déduire un lieu quand le champ structuré est absent.
const CITY_CATALOG = [
  "Paris", "Lyon", "Marseille", "Toulouse", "Bordeaux", "Lille", "Nantes",
  "Nice", "Strasbourg", "Rennes", "Montpellier", "Grenoble",
];

// Contraintes reconnues : nom canonique + motif de détection.
const CONSTRAINT_CATALOG = [
  { name: "déplacements", pattern: /d[ée]placements?|voyages? fr[ée]quents?|mobilit[ée] g[ée]ographique/i },
  { name: "astreintes", pattern: /astreintes?|on[-\s]?call|de garde/i },
  { name: "permis B", pattern: /permis b\b|permis de conduire/i },
  { name: "habilitation", pattern: /habilitation|clearance|confidentiel d[ée]fense/i },
  { name: "disponibilité immédiate", pattern: /disponibilit[ée] imm[ée]diate|asap|d[ée]s que possible/i },
  { name: "travail de nuit/week-end", pattern: /travail de nuit|week[-\s]?ends?|jours f[ée]ri[ée]s/i },
];

// --- Utilitaires -------------------------------------------------------------

// Assemble le corpus textuel d'une offre : champs structurés lisibles + données
// brutes (chaînes) éventuelles. Sert de support à toutes les heuristiques.
function collectText(offer) {
  const parts = [];
  const push = (value) => {
    if (typeof value === "string" && value.trim() !== "") parts.push(value);
  };

  push(offer.title);
  push(offer.description);
  push(offer.location);
  push(offer.compensation);

  const raw = offer.raw;
  if (typeof raw === "string") push(raw);
  else if (raw && typeof raw === "object") {
    for (const value of Object.values(raw)) push(value);
  }

  return parts.join("\n");
}

// --- Extracteurs par dimension ----------------------------------------------

// Compétences détectées, via le lexique partagé (skillLexicon).
function extractSkills(text) {
  return findSkillsInText(text);
}

// Nombre minimal d'années d'expérience exigé (borne basse d'une fourchette),
// ou null si non exprimé. Garde-fou : on n'interprète les durées « en années »
// que si le texte parle bien d'expérience (évite « il y a 3 ans »).
function extractExperienceYears(text) {
  if (!/exp[ée]ri/i.test(text)) return null;

  const years = [];
  // Fourchettes : « 3 à 5 ans », « 3-5 ans », « 3 to 5 years ».
  for (const m of text.matchAll(/(\d+)\s*(?:[-–]|à|to)\s*(\d+)\s*(?:ans?|années?|years?)/gi)) {
    years.push(parseInt(m[1], 10), parseInt(m[2], 10));
  }
  // Valeurs simples : « 5 ans », « 5+ ans », « 5 years ».
  for (const m of text.matchAll(/(\d+)\s*\+?\s*(?:ans?|années?|years?)/gi)) {
    years.push(parseInt(m[1], 10));
  }

  return years.length ? Math.min(...years) : null;
}

// Lieu : champ structuré prioritaire, sinon première ville reconnue dans le texte.
function extractLocation(offer, text) {
  if (typeof offer.location === "string" && offer.location.trim() !== "") {
    return offer.location.trim();
  }
  for (const city of CITY_CATALOG) {
    if (containsTerm(text, city)) return city;
  }
  return null;
}

// Rémunération : { min, max, period } en euros, period ∈ year|month|day.
// Reconnaît les notations en milliers (k€) et les montants explicites, en
// fourchette ou en valeur simple. Retourne null si rien d'exploitable.
function extractSalary(text) {
  const period =
    /\btjm\b|\/\s*j(?:our)?\b|par jour|journalier/i.test(text) ? "day"
    : /\/\s*mois|par mois|mensuel/i.test(text) ? "month"
    : /\/\s*an\b|par an|annuel|\d+\s*k/i.test(text) ? "year"
    : null;

  // Fourchette en milliers : « 45-55k », « 45 à 55 k€ ».
  const kRange = text.match(/(\d{2,3})\s*(?:[-–]|à|to)\s*(\d{2,3})\s*k/i);
  if (kRange) {
    return { min: Number(kRange[1]) * 1000, max: Number(kRange[2]) * 1000, period: period ?? "year" };
  }
  // Valeur simple en milliers : « 50k€ », « 50 k ».
  const kSingle = text.match(/(\d{2,3})\s*k(?:€|\s*euros?|\s*eur)?/i);
  if (kSingle) {
    const value = Number(kSingle[1]) * 1000;
    return { min: value, max: value, period: period ?? "year" };
  }
  // Montant explicite en euros : « 45 000 € », « 500€ » (TJM si contexte /jour).
  const explicit = text.match(/(\d{2,3}(?:[.\s]\d{3})+|\d{3,6})\s*(?:€|euros?|eur)/i);
  if (explicit) {
    const value = parseInt(explicit[1].replace(/[.\s]/g, ""), 10);
    return { min: value, max: value, period: period ?? "year" };
  }

  return null;
}

// Modalité de télétravail : remote | hybrid | onsite, ou null si non mentionné.
// L'ordre des tests importe : négations avant la mention générique.
function extractRemote(text) {
  if (/full[\s-]?remote|100\s*%\s*(?:t[ée]l[ée]travail|remote)|t[ée]l[ée]travail\s*(?:complet|total|intégral)/i.test(text)) {
    return "remote";
  }
  if (/(?:aucun|sans|pas de)\s+t[ée]l[ée]travail|pr[ée]sentiel|sur site|sur place|no remote/i.test(text)) {
    return "onsite";
  }
  if (/hybride|t[ée]l[ée]travail\s*partiel|\d+\s*jours?\s*(?:de\s*)?(?:t[ée]l[ée]travail|remote)|partiellement/i.test(text)) {
    return "hybrid";
  }
  // Mentionné sans précision → on suppose un télétravail partiel.
  if (/t[ée]l[ée]travail|remote/i.test(text)) return "hybrid";
  return null;
}

// Langues détectées, dans l'ordre du catalogue, sans doublon.
function extractLanguages(text) {
  const found = [];
  for (const { name, aliases } of LANGUAGE_CATALOG) {
    if (aliases.some((alias) => containsTerm(text, alias))) found.push(name);
  }
  return found;
}

// Contraintes détectées, dans l'ordre du catalogue.
function extractConstraints(text) {
  return CONSTRAINT_CATALOG.filter(({ pattern }) => pattern.test(text)).map(({ name }) => name);
}

// --- Point d'entrée ----------------------------------------------------------

// Extrait les informations clés d'une offre normalisée. Les dimensions non
// renseignées sont neutres (tableau vide ou null), jamais absentes.
function extractKeyInfo(offer = {}) {
  const text = collectText(offer);
  return {
    skills: extractSkills(text),
    contractType: offer.contractType ?? null, // champ structuré (CDI/CDD/FREELANCE)
    experienceYears: extractExperienceYears(text),
    location: extractLocation(offer, text),
    salary: extractSalary(text),
    remote: extractRemote(text),
    languages: extractLanguages(text),
    constraints: extractConstraints(text),
  };
}

module.exports = {
  extractKeyInfo,
  extractSkills,
  extractExperienceYears,
  extractLocation,
  extractSalary,
  extractRemote,
  extractLanguages,
  extractConstraints,
};
