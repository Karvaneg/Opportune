// Logs applicatifs (OPP-075). Logger structuré, déterministe, sans dépendance :
// niveaux hiérarchisés, seuil configurable (option ou LOG_LEVEL), entrées
// structurées (timestamp, level, message, contexte) et masquage des valeurs
// sensibles (tokens, secrets…) pour ne jamais divulguer de secret dans les logs
// — cohérent avec la politique de sécurité E7 (cf. config/secrets maskSecret).
//
// La sortie passe par un « sink » injectable (défaut : console), ce qui rend le
// logger entièrement testable.

// Niveaux et leur priorité croissante. Un message est émis si son niveau est
// supérieur ou égal au seuil configuré.
const LOG_LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };
const DEFAULT_LEVEL = "info";

// Valeur de remplacement pour les champs masqués (aligné sur config/secrets).
const REDACTED = "••••••••";

// Clés dont la valeur est masquée dans le contexte (comparaison insensible à la
// casse, par inclusion : « accessToken », « apiKey », « NOTION_TOKEN »… matchent).
const DEFAULT_REDACT_KEYS = ["token", "password", "secret", "apikey", "authorization", "credential"];

// Vrai si le nom de clé désigne une donnée sensible à masquer.
function isSensitiveKey(key, redactKeys) {
  const normalized = String(key).toLowerCase();
  return redactKeys.some((needle) => normalized.includes(needle));
}

// Masque récursivement les valeurs sensibles d'un objet de contexte. Les objets
// imbriqués (hors tableaux) sont parcourus ; le reste est laissé tel quel.
function redact(context, redactKeys) {
  const out = {};
  for (const [key, value] of Object.entries(context)) {
    if (isSensitiveKey(key, redactKeys)) {
      out[key] = REDACTED;
    } else if (value && typeof value === "object" && !Array.isArray(value)) {
      out[key] = redact(value, redactKeys);
    } else {
      out[key] = value;
    }
  }
  return out;
}

// Sink par défaut : écrit l'entrée sérialisée sur la console, méthode selon le
// niveau (error → console.error, warn → console.warn, sinon console.log).
function defaultSink(entry) {
  const method = entry.level === "error" ? "error" : entry.level === "warn" ? "warn" : "log";
  console[method](JSON.stringify(entry));
}

// Crée un logger. Options :
// - level : seuil minimal (défaut : LOG_LEVEL de l'environnement, sinon "info") ;
// - context : contexte de base ajouté à chaque entrée ;
// - redactKeys : clés sensibles à masquer (défaut : DEFAULT_REDACT_KEYS) ;
// - sink : fonction (entry) => void recevant l'entrée structurée (défaut console).
function createLogger(options = {}) {
  const level = options.level ?? process.env.LOG_LEVEL ?? DEFAULT_LEVEL;
  const threshold = LOG_LEVELS[level] ?? LOG_LEVELS[DEFAULT_LEVEL];
  const baseContext = options.context ?? {};
  const redactKeys = (options.redactKeys ?? DEFAULT_REDACT_KEYS).map((key) => key.toLowerCase());
  const sink = options.sink ?? defaultSink;

  // Émet une entrée si le niveau atteint le seuil. Retourne l'entrée émise, ou
  // null si elle est sous le seuil (utile pour les tests / le chaînage).
  function log(entryLevel, message, context = {}) {
    if ((LOG_LEVELS[entryLevel] ?? 0) < threshold) return null;

    const entry = {
      timestamp: new Date().toISOString(),
      level: entryLevel,
      message,
      ...redact({ ...baseContext, ...context }, redactKeys),
    };
    sink(entry);
    return entry;
  }

  return {
    level,
    debug: (message, context) => log("debug", message, context),
    info: (message, context) => log("info", message, context),
    warn: (message, context) => log("warn", message, context),
    error: (message, context) => log("error", message, context),
    // Dérive un logger enfant qui hérite de la config et enrichit le contexte.
    child: (childContext = {}) =>
      createLogger({ ...options, level, context: { ...baseContext, ...childContext } }),
  };
}

// Instance par défaut, prête à l'emploi.
const logger = createLogger();

module.exports = { LOG_LEVELS, DEFAULT_LEVEL, REDACTED, createLogger, logger };
