const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  adaptResumeToOffer,
  collectProfileSkills,
  tailorExperiences,
  tailorLanguages,
} = require("./resumeAdapter");

// --- collectProfileSkills ---

test("collectProfileSkills : fusionne structuré + legacy, dédup, conserve le libellé", () => {
  const profile = {
    structuredSkills: [{ name: "React" }, { name: "PostgreSQL" }],
    skills: ["JavaScript", "react"], // doublon insensible à la casse
  };
  assert.deepEqual(collectProfileSkills(profile).map((s) => s.name), [
    "React",
    "PostgreSQL",
    "JavaScript",
  ]);
});

// --- tailorExperiences ---

test("tailorExperiences : trie par pertinence, contenu inchangé", () => {
  const experiences = ["Dev backend Java chez X", "Lead React chez Y", "Stage SQL"];
  const result = tailorExperiences(experiences, ["React", "SQL"]);
  assert.deepEqual(result, ["Lead React chez Y", "Stage SQL", "Dev backend Java chez X"]);
  // même ensemble d'éléments (aucune perte, aucun ajout)
  assert.deepEqual([...result].sort(), [...experiences].sort());
});

// --- tailorLanguages ---

test("tailorLanguages : place d'abord les langues attendues par l'offre", () => {
  assert.deepEqual(tailorLanguages(["Français", "Anglais"], ["anglais"]), ["Anglais", "Français"]);
});

// --- adaptResumeToOffer ---

const PROFILE = {
  id: "p1",
  name: "Marie",
  contractType: "les deux",
  structuredSkills: [{ name: "React" }, { name: "PostgreSQL" }, { name: "Docker" }],
  skills: ["JavaScript"],
  experiences: ["Backend Java", "Lead React/PostgreSQL"],
  languages: ["Français", "Anglais"],
};

const OFFER_KEY_INFO = {
  skills: ["React", "SQL", "Kubernetes"], // Kubernetes non détenu
  languages: ["anglais"],
};

test("adaptResumeToOffer : met en avant les compétences attendues, réordonne", () => {
  const cv = adaptResumeToOffer(PROFILE, OFFER_KEY_INFO, { resumeId: "cv-42" });

  assert.deepEqual(cv.skills.map((s) => s.name), ["React", "PostgreSQL", "Docker", "JavaScript"]);
  assert.deepEqual(cv.highlightedSkills, ["React", "PostgreSQL"]);
  assert.equal(cv.name, "Marie");
  assert.equal(cv.profileId, "p1");
  assert.equal(cv.sourceResumeId, "cv-42");
  assert.deepEqual(cv.languages, ["Anglais", "Français"]);
});

test("adaptResumeToOffer : FIDÉLITÉ — n'inclut aucun élément hors profil", () => {
  const cv = adaptResumeToOffer(PROFILE, OFFER_KEY_INFO);

  const profileSkillNames = new Set(collectProfileSkills(PROFILE).map((s) => s.name.toLowerCase()));
  // Toute compétence du CV vient du profil
  for (const skill of cv.skills) {
    assert.ok(profileSkillNames.has(skill.name.toLowerCase()), `compétence inventée : ${skill.name}`);
  }
  // La compétence manquante est signalée à part, jamais intégrée au CV
  assert.deepEqual(cv.missingSkills, ["Kubernetes"]);
  assert.ok(!cv.skills.some((s) => s.name === "Kubernetes"));
  // Les expériences du CV sont exactement celles du profil (réordonnées)
  assert.deepEqual([...cv.experiences].sort(), [...PROFILE.experiences].sort());
});

test("adaptResumeToOffer : profil et offre vides → structure neutre", () => {
  const cv = adaptResumeToOffer({}, {});
  assert.deepEqual(cv, {
    profileId: null,
    name: "",
    contractType: null,
    skills: [],
    highlightedSkills: [],
    missingSkills: [],
    experiences: [],
    languages: [],
    sourceResumeId: null,
  });
});
