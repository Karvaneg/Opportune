const { test } = require("node:test");
const assert = require("node:assert/strict");

const { formatDossier, formatPipelineReport } = require("./pipelineReport");

// Dossier retenu minimal (forme produite par applicationPipeline.processOffer).
function persistedDossier() {
  return {
    offer: { title: "Développeur Fullstack", company: "Alma", contractType: "CDI", location: "Paris" },
    category: "CDI",
    score: 88,
    recommendation: { action: "postuler", label: "Candidater", score: 88 },
    reasons: { positives: ["Compétences : react, node.js"], negatives: [] },
    risks: [],
    persisted: true,
    application: { followUpAt: "2026-09-10" },
    documents: [{ type: "cv" }, { type: "coverLetter" }, { type: "linkedInMessage" }],
  };
}

// Dossier non retenu (offre hors préférences ou score faible).
function ignoredDossier() {
  return {
    offer: { title: "Chargé de communication", company: "MediaPlus", contractType: "CDD", location: "Nantes" },
    category: "À ignorer",
    score: 20,
    recommendation: { action: "ignorer", label: "Ignorer", score: 20 },
    reasons: { positives: [], negatives: ["Type de contrat non désiré (offre CDD, profil CDI)"] },
    risks: ["Compétence exigée non détenue : communication"],
    persisted: false,
    application: null,
    documents: [],
  };
}

test("formatDossier : offre retenue affiche score, reco, catégorie et candidature", () => {
  const out = formatDossier(persistedDossier());
  assert.match(out, /Développeur Fullstack — Alma/);
  assert.match(out, /Score 88\/100/);
  assert.match(out, /Candidater/);
  assert.match(out, /Catégorie CDI/);
  assert.match(out, /Candidature créée \(3 doc\(s\), relance 2026-09-10\)/);
});

test("formatDossier : offre non retenue signale l'absence de candidature", () => {
  const out = formatDossier(ignoredDossier());
  assert.match(out, /Non retenue/);
  assert.match(out, /Type de contrat non désiré/);
  assert.match(out, /Compétence exigée non détenue/);
  assert.doesNotMatch(out, /Candidature créée/);
});

test("formatPipelineReport : en-tête profil + récapitulatif + un bloc par offre", () => {
  const profile = { name: "Alex Martin", contractType: "CDI", skills: ["React", "Node.js"] };
  const out = formatPipelineReport([persistedDossier(), ignoredDossier()], { profile });

  assert.match(out, /Profil : Alex Martin \(CDI\)/);
  assert.match(out, /Compétences : React, Node\.js/);
  assert.match(out, /2 offre\(s\) analysée\(s\) · 1 candidature\(s\) créée\(s\)/);
  // Les deux offres apparaissent.
  assert.match(out, /Alma/);
  assert.match(out, /MediaPlus/);
});

test("formatPipelineReport : liste vide reste lisible", () => {
  const out = formatPipelineReport([], { profile: { name: "Test" } });
  assert.match(out, /0 offre\(s\) analysée\(s\) · 0 candidature\(s\) créée\(s\)/);
});
