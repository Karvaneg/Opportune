// Démo CLI du pipeline de candidature (OPP-088). Point d'entrée tangible : fait
// tourner l'orchestrateur (applicationPipeline) sur le jeu d'offres de test
// (sampleOffers) avec un profil de démonstration, puis affiche le rapport
// (score, raisons, recommandation, candidatures créées).
//
// Reproductible : le pipeline persiste dans un stockage TEMPORAIRE isolé, remis à
// zéro à chaque lancement — la démo ne pollue jamais le dossier data/ du projet.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const { processOffers } = require("./services");
const { sampleOffers } = require("./fixtures");
const { formatPipelineReport } = require("./display");

// Profil de démonstration : un développeur fullstack en CDI, aligné sur une partie
// seulement du jeu d'offres (pour illustrer des scores et décisions variés).
const DEMO_PROFILE = {
  id: "demo-profile",
  name: "Alex Martin",
  contractType: "CDI",
  skills: ["React", "Node.js", "PostgreSQL", "JavaScript", "TypeScript"],
  totalExperienceYears: 6,
  location: "Paris",
  remote: "full remote",
  targetSalary: 50000,
  languages: ["français", "anglais"],
};

// Stockage temporaire isolé, remis à zéro à chaque exécution (reproductibilité).
function freshDemoStores() {
  const dir = path.join(os.tmpdir(), "opportune-demo");
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  return {
    applicationsPath: path.join(dir, "applications.json"),
    documentsPath: path.join(dir, "documentVersions.json"),
  };
}

function main() {
  const stores = freshDemoStores();
  const dossiers = processOffers(sampleOffers(), DEMO_PROFILE, stores);
  console.log(formatPipelineReport(dossiers, { profile: DEMO_PROFILE }));
  console.log(`\n💾 Candidatures & documents persistés dans : ${path.dirname(stores.applicationsPath)}`);
}

main();
