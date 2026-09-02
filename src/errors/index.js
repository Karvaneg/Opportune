// Gestion robuste des erreurs (OPP-076). Hiérarchie d'erreurs typées, portant un
// `code` stable et un indicateur `operational` (erreur attendue et gérable vs
// bug inattendu), plus un normaliseur qui présente une erreur de façon sûre —
// sans divulguer les détails internes des bugs.

// Erreur de base de l'application. Les sous-classes fixent un code stable.
class OpportuneError extends Error {
  constructor(message, { code = "OPPORTUNE_ERROR", operational = true, details } = {}) {
    super(message);
    this.name = new.target.name; // nom réel de la sous-classe
    this.code = code;
    this.operational = operational;
    if (details !== undefined) this.details = details;
  }
}

// Donnée invalide (profil, offre, candidature…).
class ValidationError extends OpportuneError {
  constructor(message, details) {
    super(message, { code: "VALIDATION", operational: true, details });
  }
}

// Ressource introuvable (candidature, CV…).
class NotFoundError extends OpportuneError {
  constructor(message, details) {
    super(message, { code: "NOT_FOUND", operational: true, details });
  }
}

// Transition de statut non autorisée (machine à états des candidatures).
class InvalidTransitionError extends OpportuneError {
  constructor(message, details) {
    super(message, { code: "INVALID_TRANSITION", operational: true, details });
  }
}

// Problème de configuration / secret manquant.
class ConfigError extends OpportuneError {
  constructor(message, details) {
    super(message, { code: "CONFIG", operational: true, details });
  }
}

// Envoi refusé par le sas de validation (anti-invention / confirmation).
class SendBlockedError extends OpportuneError {
  constructor(message, details) {
    super(message, { code: "SEND_BLOCKED", operational: true, details });
  }
}

// Normalise n'importe quelle valeur levée en { code, message, operational }.
// Les OpportuneError conservent leur code, message et détails. Toute autre erreur
// est traitée comme un bug interne : code INTERNAL, non operational, message
// générique (on ne divulgue pas le message d'origine, potentiellement sensible).
function normalizeError(error) {
  if (error instanceof OpportuneError) {
    const normalized = { code: error.code, message: error.message, operational: error.operational };
    if (error.details !== undefined) normalized.details = error.details;
    return normalized;
  }
  return { code: "INTERNAL", message: "Une erreur interne est survenue", operational: false };
}

module.exports = {
  OpportuneError,
  ValidationError,
  NotFoundError,
  InvalidTransitionError,
  ConfigError,
  SendBlockedError,
  normalizeError,
};
