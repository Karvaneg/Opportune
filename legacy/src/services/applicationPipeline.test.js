const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const os = require("node:os");

const { processOffer, processOffers } = require("./applicationPipeline");
const { listApplications, getApplication } = require("./applicationService");
const { listVersions } = require("./documentVersionService");
const { sampleOffers } = require("../fixtures");

// Stores temporaires isolés par test (candidatures + versions de documents).
function tmpStores() {
  const stamp = process.hrtime.bigint();
  return {
    applicationsPath: path.join(os.tmpdir(), `pipeline-apps-${stamp}.json`),
    documentsPath: path.join(os.tmpdir(), `pipeline-docs-${stamp}.json`),
  };
}

// Profil fortement aligné sur l'offre CDI React/Node (sample-1).
function fullstackProfile() {
  return {
    id: "profile-1",
    name: "Alex Martin",
    contractType: "CDI",
    skills: ["React", "Node.js", "PostgreSQL", "JavaScript"],
    totalExperienceYears: 6,
    location: "Paris",
    remote: "full remote",
    targetSalary: 50000,
    languages: ["français", "anglais"],
  };
}

// Profil freelance, aligné sur la mission Data Engineer (sample-2).
function freelanceProfile() {
  return {
    id: "profile-2",
    name: "Sam Indé",
    contractType: "freelance",
    skills: ["Python", "SQL", "Airflow"],
    totalExperienceYears: 5,
    location: "Lyon",
    remote: "hybride",
    targetDailyRate: 500,
    availability: "immédiate",
    languages: ["français"],
  };
}

// Retrouve une offre du jeu de test par son id brut.
function sampleOfferById(id) {
  return sampleOffers().find((offer) => offer.id === id);
}

// --- Analyse toujours produite ---

test("processOffer : produit un dossier d'analyse (score, reco, catégorie, risques)", () => {
  const stores = tmpStores();
  const offer = sampleOfferById("sample-1");
  const dossier = processOffer(offer, fullstackProfile(), stores);

  assert.equal(typeof dossier.score, "number");
  assert.ok(dossier.score >= 0 && dossier.score <= 100);
  assert.ok(["postuler", "a_etudier", "ignorer"].includes(dossier.recommendation.action));
  assert.equal(dossier.category, "CDI");
  assert.ok(Array.isArray(dossier.risks));
  assert.ok(dossier.keyInfo.skills.includes("React"));
});

// --- Offre retenue : candidature persistée + documents versionnés + relance ---

test("processOffer : une offre alignée crée une candidature persistée et scorée", () => {
  const stores = tmpStores();
  const offer = sampleOfferById("sample-1");
  const dossier = processOffer(offer, fullstackProfile(), stores);

  assert.equal(dossier.persisted, true);
  assert.ok(dossier.application);
  assert.equal(dossier.application.profileId, "profile-1");
  assert.equal(dossier.application.offerId, offer.id);
  assert.equal(dossier.application.score, dossier.score);

  // Persistée pour de vrai dans le store injecté.
  const stored = listApplications("profile-1", stores.applicationsPath);
  assert.equal(stored.length, 1);
  assert.equal(stored[0].id, dossier.application.id);
});

test("processOffer : versionne CV, lettre et message LinkedIn pour l'offre", () => {
  const stores = tmpStores();
  const offer = sampleOfferById("sample-1");
  const dossier = processOffer(offer, fullstackProfile(), stores);

  assert.equal(dossier.documents.length, 3);
  const types = dossier.documents.map((d) => d.type).sort();
  assert.deepEqual(types, ["coverLetter", "cv", "linkedInMessage"]);
  for (const version of dossier.documents) {
    assert.equal(version.version, 1);
    assert.equal(version.offerId, offer.id);
  }

  // La candidature référence les documents versionnés.
  assert.equal(dossier.application.documents.length, 3);
  assert.ok(dossier.application.documents.every((d) => typeof d.ref === "string"));

  // Réellement présents dans le store de versions.
  const persistedVersions = listVersions(offer.id, null, stores.documentsPath);
  assert.equal(persistedVersions.length, 3);
});

test("processOffer : planifie une relance automatique sur la candidature", () => {
  const stores = tmpStores();
  const offer = sampleOfferById("sample-1");
  const dossier = processOffer(offer, fullstackProfile(), stores);

  assert.ok(dossier.application.followUpAt, "une date de relance est posée");
  const reloaded = getApplication(dossier.application.id, stores.applicationsPath);
  assert.equal(reloaded.followUpAt, dossier.application.followUpAt);
});

test("processOffer : followUp=false n'ajoute pas de relance", () => {
  const stores = tmpStores();
  const offer = sampleOfferById("sample-1");
  const dossier = processOffer(offer, fullstackProfile(), { ...stores, followUp: false });

  assert.equal(dossier.persisted, true);
  assert.equal(dossier.application.followUpAt, null);
});

// --- Versionnage : une seconde passe conserve et incrémente ---

test("processOffer : re-traiter la même offre incrémente les versions (aucun écrasement)", () => {
  const stores = tmpStores();
  const offer = sampleOfferById("sample-1");
  const profile = fullstackProfile();

  processOffer(offer, profile, stores);
  const second = processOffer(offer, profile, stores);

  const cvVersions = listVersions(offer.id, "cv", stores.documentsPath);
  assert.deepEqual(cvVersions.map((v) => v.version), [1, 2]);
  assert.ok(second.documents.find((d) => d.type === "cv").version === 2);
});

test("processOffer : une offre FREELANCE génère une proposition (pas de lettre)", () => {
  const stores = tmpStores();
  const offer = sampleOfferById("sample-2");
  const dossier = processOffer(offer, freelanceProfile(), { ...stores, persist: true });

  assert.equal(dossier.persisted, true);
  const types = dossier.documents.map((d) => d.type).sort();
  assert.deepEqual(types, ["cv", "freelanceProposal", "linkedInMessage"]);
});

// --- Décision : offres non retenues ---

test("processOffer : une offre hors préférences de contrat n'est pas persistée", () => {
  const stores = tmpStores();
  // sample-2 est en Freelance ; le profil ne vise que le CDI → « À ignorer ».
  const offer = sampleOfferById("sample-2");
  const dossier = processOffer(offer, fullstackProfile(), stores);

  assert.equal(dossier.category, "À ignorer");
  assert.equal(dossier.persisted, false);
  assert.equal(dossier.application, null);
  assert.deepEqual(dossier.documents, []);
  assert.equal(listApplications("profile-1", stores.applicationsPath).length, 0);
});

test("processOffer : persist=false force un dry-run (analyse seule)", () => {
  const stores = tmpStores();
  const offer = sampleOfferById("sample-1");
  const dossier = processOffer(offer, fullstackProfile(), { ...stores, persist: false });

  assert.equal(dossier.persisted, false);
  assert.equal(dossier.application, null);
  assert.equal(dossier.documents.length, 0);
  assert.equal(listVersions(offer.id, null, stores.documentsPath).length, 0);
});

test("processOffer : persist=true force la création malgré une reco faible", () => {
  const stores = tmpStores();
  // sample-3 (CDD, communication) mal aligné avec un profil dev → reco faible.
  const offer = sampleOfferById("sample-3");
  const dossier = processOffer(offer, fullstackProfile(), { ...stores, persist: true });

  assert.equal(dossier.persisted, true);
  assert.ok(dossier.application);
});

// --- Lot ---

test("processOffers : traite un jeu d'offres et ne persiste que les retenues", () => {
  const stores = tmpStores();
  const offers = sampleOffers();
  const dossiers = processOffers(offers, fullstackProfile(), stores);

  assert.equal(dossiers.length, offers.length);

  const persistedCount = dossiers.filter((d) => d.persisted).length;
  const storedCount = listApplications("profile-1", stores.applicationsPath).length;
  assert.equal(persistedCount, storedCount);
  assert.ok(persistedCount >= 1, "au moins une offre CDI alignée est retenue");
});
