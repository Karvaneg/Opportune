// Sas d'envoi d'une candidature (OPP-053). Critère du ticket : une confirmation
// explicite est obligatoire — rien ne doit pouvoir partir sans validation humaine.
//
// Deux barrières, toutes deux nécessaires pour autoriser un envoi :
//   1. ANTI-INVENTION : la candidature passe le garde-fou (inventionGuard) —
//      aucune candidature qui invente ne peut être envoyée ;
//   2. CONFIRMATION HUMAINE EXPLICITE : l'appelant fournit `confirmed === true`.
//      Par défaut (confirmation absente, ou autre valeur), l'envoi est bloqué.
//
// L'envoi réel n'existe pas encore (pas de connecteur au MVP) : ce module fournit
// le point de passage obligé que tout futur envoi devra franchir (performSend).
const { verifyApplication } = require("./inventionGuard");
const { SendBlockedError } = require("../errors");

// Codes de blocage stables (exploitables par l'UI).
const BLOCK_REASONS = {
  INVENTION: "invention_detectee",
  CONFIRMATION: "confirmation_requise",
};

// Décide si une candidature peut être envoyée. Retourne
// { authorized, reasons, verification } : authorized vrai seulement si aucune
// barrière n'est levée. `reasons` liste les blocages (codes BLOCK_REASONS).
function authorizeSend(application = {}, confirmation = {}) {
  const { profile, adaptedResume, coverLetter } = application;
  const reasons = [];

  // Barrière 1 — anti-invention.
  const verification = verifyApplication({ adaptedResume, coverLetter }, profile ?? {});
  if (!verification.ok) reasons.push(BLOCK_REASONS.INVENTION);

  // Barrière 2 — confirmation humaine explicite (strictement `true`).
  if (confirmation?.confirmed !== true) reasons.push(BLOCK_REASONS.CONFIRMATION);

  return { authorized: reasons.length === 0, reasons, verification };
}

// Exécute l'envoi réel (`send`, injecté par l'appelant) UNIQUEMENT si le sas
// l'autorise. Sinon lève une erreur explicite et n'appelle jamais `send` : c'est
// le blocage effectif de tout envoi non confirmé ou non fidèle.
function performSend(application, confirmation, send) {
  const decision = authorizeSend(application, confirmation);
  if (!decision.authorized) {
    throw new SendBlockedError(`Envoi bloqué : ${decision.reasons.join(", ")}`, { reasons: decision.reasons });
  }
  if (typeof send !== "function") {
    throw new Error("performSend : la fonction d'envoi (send) est requise");
  }
  return send(application);
}

module.exports = { BLOCK_REASONS, authorizeSend, performSend };
