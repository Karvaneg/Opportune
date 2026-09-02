// Modèle d'une version de document généré (OPP-045). Chaque (re)génération ou
// édition d'un document de candidature produit une version immuable, horodatée,
// numérotée et associée à une offre. La logique de versionnage (numérotation,
// conservation, consultation) vit dans src/services/documentVersionService.js ;
// la persistance dans src/models/documentVersionStore.js.
const { randomUUID } = require("node:crypto");

// Types de documents générés versionnables (cohérent avec les générateurs E4 :
// resumeAdapter, coverLetterGenerator, linkedInMessageGenerator).
const DOCUMENT_TYPES = ["cv", "coverLetter", "linkedInMessage"];

// Champs obligatoires : une version est toujours rattachée à une offre et typée.
const REQUIRED_FIELDS = ["offerId", "type"];

// Construit une version de document à partir de données partielles.
// Un id est généré si absent ; createdAt est daté à la construction. Le numéro de
// version est normalement attribué par le service (défaut 1).
function createDocumentVersion(data = {}) {
  return {
    id: data.id ?? randomUUID(),
    offerId: data.offerId ?? null, // offre associée — obligatoire
    type: data.type ?? null, // type de document (DOCUMENT_TYPES) — obligatoire
    version: data.version ?? 1, // numéro de version (≥ 1), attribué par le service
    content: data.content ?? null, // contenu du document (objet structuré ou texte)
    label: data.label ?? null, // libellé libre optionnel (ex. « après relecture »)
    createdAt: data.createdAt ?? new Date().toISOString(),
  };
}

module.exports = { DOCUMENT_TYPES, REQUIRED_FIELDS, createDocumentVersion };
