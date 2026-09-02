const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  extractKeyInfo,
  extractSkills,
  extractExperienceYears,
  extractLocation,
  extractSalary,
  extractRemote,
  extractLanguages,
  extractConstraints,
} = require("./offerKeyInfoExtractor");

// --- extractSkills ---

test("extractSkills : détecte les compétences par nom canonique et variantes", () => {
  const skills = extractSkills("Stack : React.js, nodejs, TypeScript et PostgreSQL.");
  assert.deepEqual(skills, ["TypeScript", "Node.js", "React", "SQL"]);
});

test("extractSkills : gère les noms à ponctuation (c++, c#, .net)", () => {
  assert.deepEqual(extractSkills("Expérience en C++ appréciée"), ["C++"]);
  assert.deepEqual(extractSkills("Environnement .NET / C#"), ["C#"]);
});

test("extractSkills : reconnaît frameworks, BaaS, plateformes, devops et méthodo", () => {
  const skills = extractSkills(
    "Back Symfony, base Supabase et Neon, déploiement sur Vercel et Render, " +
      "culture DevOps, méthodo Agile.",
  );
  assert.deepEqual(skills, [
    "Symfony",
    "Supabase",
    "Neon",
    "Vercel",
    "Render",
    "DevOps",
    "Agile",
  ]);
});

test("extractSkills : Notion et Render exigent la majuscule (anti faux positif)", () => {
  // Formes outils (majuscule) → détectées
  assert.deepEqual(extractSkills("Docs sur Notion, hébergé sur Render"), [
    "Render",
    "Notion",
  ]);
  // Mots courants (minuscule) → ignorés
  assert.deepEqual(extractSkills("Quelques notions de React et du server-side render"), [
    "React",
  ]);
});

test("extractSkills : pas de faux positif sur un sous-mot", () => {
  // « javascript » ne doit pas matcher via « java »
  assert.deepEqual(extractSkills("Nous faisons du javascript"), ["JavaScript"]);
  assert.deepEqual(extractSkills("Aucune techno listée ici"), []);
});

// --- extractExperienceYears ---

test("extractExperienceYears : valeur simple et notation +", () => {
  assert.equal(extractExperienceYears("5 ans d'expérience exigés"), 5);
  assert.equal(extractExperienceYears("Expérience : 3+ ans"), 3);
});

test("extractExperienceYears : fourchette → borne basse", () => {
  assert.equal(extractExperienceYears("Expérience de 3 à 5 ans"), 3);
  assert.equal(extractExperienceYears("2-4 years of experience"), 2);
});

test("extractExperienceYears : durée sans contexte d'expérience → null", () => {
  assert.equal(extractExperienceYears("Société créée il y a 10 ans"), null);
  assert.equal(extractExperienceYears("Poste sans mention de durée"), null);
});

// --- extractLocation ---

test("extractLocation : champ structuré prioritaire", () => {
  assert.equal(extractLocation({ location: " Nantes " }, "peu importe le texte"), "Nantes");
});

test("extractLocation : repli sur une ville reconnue dans le texte", () => {
  assert.equal(extractLocation({ location: null }, "Poste basé à Lyon centre"), "Lyon");
  assert.equal(extractLocation({}, "Aucune ville ici"), null);
});

// --- extractSalary ---

test("extractSalary : fourchette et valeur simple en k€", () => {
  assert.deepEqual(extractSalary("Rémunération 45-55k€"), { min: 45000, max: 55000, period: "year" });
  assert.deepEqual(extractSalary("Salaire : 50k€ annuel"), { min: 50000, max: 50000, period: "year" });
});

test("extractSalary : TJM en euros/jour", () => {
  assert.deepEqual(extractSalary("TJM 500€ / jour"), { min: 500, max: 500, period: "day" });
});

test("extractSalary : montant annuel explicite", () => {
  assert.deepEqual(extractSalary("Package 45 000 € brut par an"), { min: 45000, max: 45000, period: "year" });
});

test("extractSalary : rien d'exploitable → null", () => {
  assert.equal(extractSalary("Rémunération selon profil"), null);
});

// --- extractRemote ---

test("extractRemote : full remote, hybride, présentiel", () => {
  assert.equal(extractRemote("Full remote possible"), "remote");
  assert.equal(extractRemote("Télétravail complet"), "remote");
  assert.equal(extractRemote("2 jours de télétravail par semaine"), "hybrid");
  assert.equal(extractRemote("Poste en présentiel"), "onsite");
});

test("extractRemote : négation avant mention générique", () => {
  assert.equal(extractRemote("Aucun télétravail pour ce poste"), "onsite");
});

test("extractRemote : mention simple → hybrid, absence → null", () => {
  assert.equal(extractRemote("Télétravail possible"), "hybrid");
  assert.equal(extractRemote("Pas d'info sur ce point"), null);
});

// --- extractLanguages ---

test("extractLanguages : détecte les langues multilingues", () => {
  assert.deepEqual(extractLanguages("Anglais courant, français bilingue"), ["français", "anglais"]);
  assert.deepEqual(extractLanguages("Fluent English and German"), ["anglais", "allemand"]);
});

// --- extractConstraints ---

test("extractConstraints : détecte plusieurs contraintes", () => {
  const constraints = extractConstraints("Déplacements fréquents, astreintes et permis B requis");
  assert.deepEqual(constraints, ["déplacements", "astreintes", "permis B"]);
});

test("extractConstraints : aucune contrainte → tableau vide", () => {
  assert.deepEqual(extractConstraints("Poste standard sans particularité"), []);
});

// --- extractKeyInfo (intégration) ---

test("extractKeyInfo : agrège toutes les dimensions depuis une offre", () => {
  const offer = {
    title: "Développeur Node.js React",
    company: "ACME",
    location: "Paris",
    compensation: "45-55k€",
    description:
      "Nous cherchons un développeur avec 4 ans d'expérience en TypeScript. " +
      "Télétravail partiel (2 jours). Anglais courant. Déplacements ponctuels.",
    raw: { extra: "PostgreSQL apprécié" },
  };

  const info = extractKeyInfo(offer);

  assert.deepEqual(info.skills, ["TypeScript", "Node.js", "React", "SQL"]);
  assert.equal(info.experienceYears, 4);
  assert.equal(info.location, "Paris");
  assert.deepEqual(info.salary, { min: 45000, max: 55000, period: "year" });
  assert.equal(info.remote, "hybrid");
  assert.deepEqual(info.languages, ["anglais"]);
  assert.deepEqual(info.constraints, ["déplacements"]);
});

test("extractKeyInfo : offre vide → dimensions neutres, jamais absentes", () => {
  const info = extractKeyInfo({});
  assert.deepEqual(info, {
    skills: [],
    contractType: null,
    experienceYears: null,
    location: null,
    salary: null,
    remote: null,
    languages: [],
    constraints: [],
  });
});
