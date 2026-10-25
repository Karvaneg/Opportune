const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  findUnsupportedSkills,
  verifyText,
  verifyAdaptedResume,
  verifyCoverLetter,
  verifyApplication,
} = require("./inventionGuard");

const PROFILE = {
  name: "Marie",
  structuredSkills: [{ name: "React" }, { name: "PostgreSQL" }],
  skills: ["JavaScript"],
  experiences: ["Lead React chez Y", "Backend Java"],
};

// --- findUnsupportedSkills / verifyText ---

test("findUnsupportedSkills : signale les outils absents du profil", () => {
  // React et SQL (PostgreSQL) détenus ; Kubernetes non
  assert.deepEqual(
    findUnsupportedSkills("Maîtrise de React, PostgreSQL et Kubernetes", PROFILE),
    ["Kubernetes"],
  );
});

test("verifyText : ok quand tout est supporté", () => {
  assert.deepEqual(verifyText("Solide en React et JavaScript", PROFILE), {
    ok: true,
    unsupportedSkills: [],
  });
});

// --- verifyAdaptedResume ---

test("verifyAdaptedResume : CV fidèle → ok", () => {
  const cv = {
    skills: [{ name: "React" }, { name: "PostgreSQL" }, { name: "JavaScript" }],
    experiences: ["Lead React chez Y", "Backend Java"],
  };
  assert.deepEqual(verifyAdaptedResume(cv, PROFILE), {
    ok: true,
    unsupportedSkills: [],
    unsupportedExperiences: [],
  });
});

test("verifyAdaptedResume : détecte compétence et expérience inventées", () => {
  const tampered = {
    skills: [{ name: "React" }, { name: "Kubernetes" }],
    experiences: ["Lead React chez Y", "CTO chez FictionCorp"],
  };
  const result = verifyAdaptedResume(tampered, PROFILE);
  assert.equal(result.ok, false);
  assert.deepEqual(result.unsupportedSkills, ["Kubernetes"]);
  assert.deepEqual(result.unsupportedExperiences, ["CTO chez FictionCorp"]);
});

test("verifyAdaptedResume : libellé différent mais même compétence canonique → supporté", () => {
  // Profil a PostgreSQL ; CV liste SQL (même canonique) → pas une invention
  const cv = { skills: [{ name: "SQL" }], experiences: [] };
  assert.equal(verifyAdaptedResume(cv, PROFILE).ok, true);
});

// --- verifyCoverLetter ---

test("verifyCoverLetter : contrôle les compétences mises en avant", () => {
  assert.equal(verifyCoverLetter({ highlightedSkills: ["React", "PostgreSQL"] }, PROFILE).ok, true);
  const bad = verifyCoverLetter({ highlightedSkills: ["React", "Kubernetes"] }, PROFILE);
  assert.equal(bad.ok, false);
  assert.deepEqual(bad.unsupportedSkills, ["Kubernetes"]);
});

// --- verifyApplication ---

test("verifyApplication : agrège CV + lettre, ok si les deux passent", () => {
  const report = verifyApplication(
    {
      adaptedResume: { skills: [{ name: "React" }], experiences: ["Backend Java"] },
      coverLetter: { highlightedSkills: ["React"] },
    },
    PROFILE,
  );
  assert.equal(report.ok, true);
  assert.equal(report.resume.ok, true);
  assert.equal(report.letter.ok, true);
});

test("verifyApplication : ok=false si un artefact invente ; artefacts absents ignorés", () => {
  const report = verifyApplication(
    { coverLetter: { highlightedSkills: ["Kubernetes"] } },
    PROFILE,
  );
  assert.equal(report.ok, false);
  assert.equal(report.resume, null); // non fourni → ignoré
  assert.equal(report.letter.ok, false);
});
