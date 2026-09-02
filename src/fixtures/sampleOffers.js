// Jeu d'offres de test (OPP-086). Offres « brutes » réalistes, aux champs
// hétérogènes (comme les sources réelles), destinées aux tests d'intégration et
// à la démonstration du pipeline (normalisation → analyse → score → candidature).
// Volontairement variées : CDI / CDD / Freelance, télétravail/présentiel, salaire
// annuel ou TJM, contraintes, compétences partielles, et une offre minimale.
const { normalizeOffer } = require("../services/offerNormalizer");

// Offres brutes (avant normalisation), avec des alias de champs différents d'une
// source à l'autre pour exercer aussi le normaliseur (offerNormalizer).
const SAMPLE_RAW_OFFERS = [
  {
    id: "sample-1",
    titre: "Développeur Fullstack React/Node",
    entreprise: "Alma",
    source: "linkedin",
    lien: "https://exemple.test/offres/1",
    type: "CDI",
    ville: "Paris",
    salaire: "45-55k€",
    description:
      "Stack React, Node.js et PostgreSQL. Full remote. Anglais courant. " +
      "4 ans d'expérience minimum.",
  },
  {
    id: "sample-2",
    poste: "Consultant Data Engineer",
    client: "DataCorp",
    source: "malt",
    url: "https://exemple.test/offres/2",
    contract: "Freelance",
    localisation: "Lyon",
    tjm: "550€/jour",
    description:
      "Mission Python, SQL et Airflow. Télétravail partiel (2 jours). " +
      "Déplacements ponctuels. 3 ans d'expérience.",
  },
  {
    id: "sample-3",
    titre: "Chargé de communication",
    entreprise: "MediaPlus",
    source: "indeed",
    lien: "https://exemple.test/offres/3",
    type: "CDD",
    ville: "Nantes",
    description: "Poste en présentiel. Community management et événementiel.",
  },
  {
    id: "sample-4",
    titre: "Ingénieur Backend Java",
    entreprise: "AeroSoft",
    source: "linkedin",
    lien: "https://exemple.test/offres/4",
    type: "CDI",
    ville: "Toulouse",
    salaire: "50k€",
    description:
      "Java, Spring et Kubernetes. Astreintes. Permis B requis. " +
      "5 ans d'expérience.",
  },
  {
    id: "sample-5",
    titre: "Développeur Frontend Vue.js",
    entreprise: "Webagency",
    source: "welcometothejungle",
    lien: "https://exemple.test/offres/5",
    type: "CDI",
    ville: "Remote",
    salaire: "40-48k€",
    description: "Vue.js, TypeScript et Tailwind. Full remote. Anglais professionnel.",
  },
  {
    // Offre minimale : juste les champs obligatoires (robustesse).
    id: "sample-6",
    titre: "Développeur",
    entreprise: "StartupX",
    source: "linkedin",
    lien: "https://exemple.test/offres/6",
    type: "CDI",
  },
];

// Retourne les offres du jeu de test, normalisées vers le modèle jobOffer.
function sampleOffers() {
  return SAMPLE_RAW_OFFERS.map(normalizeOffer);
}

module.exports = { SAMPLE_RAW_OFFERS, sampleOffers };
