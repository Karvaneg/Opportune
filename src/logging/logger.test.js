const { test } = require("node:test");
const assert = require("node:assert/strict");

const { createLogger, LOG_LEVELS, REDACTED } = require("./logger");

// Sink de test : collecte les entrées structurées émises.
function captureSink() {
  const entries = [];
  return { entries, sink: (entry) => entries.push(entry) };
}

// --- Structure des entrées ---

test("logger : émet une entrée structurée (timestamp, level, message, contexte)", () => {
  const { entries, sink } = captureSink();
  const logger = createLogger({ level: "debug", sink });

  logger.info("candidature enregistrée", { applicationId: "a1" });

  assert.equal(entries.length, 1);
  const [entry] = entries;
  assert.equal(entry.level, "info");
  assert.equal(entry.message, "candidature enregistrée");
  assert.equal(entry.applicationId, "a1");
  assert.match(entry.timestamp, /^\d{4}-\d{2}-\d{2}T/);
});

test("logger : expose une méthode par niveau", () => {
  const { entries, sink } = captureSink();
  const logger = createLogger({ level: "debug", sink });
  logger.debug("d");
  logger.info("i");
  logger.warn("w");
  logger.error("e");
  assert.deepEqual(entries.map((e) => e.level), ["debug", "info", "warn", "error"]);
});

// --- Seuil de niveau ---

test("logger : ignore les messages sous le seuil configuré", () => {
  const { entries, sink } = captureSink();
  const logger = createLogger({ level: "warn", sink });

  assert.equal(logger.debug("d"), null);
  assert.equal(logger.info("i"), null);
  assert.ok(logger.warn("w")); // émis
  assert.ok(logger.error("e")); // émis
  assert.deepEqual(entries.map((e) => e.level), ["warn", "error"]);
});

test("logger : le seuil par défaut est info (debug ignoré)", () => {
  const { entries, sink } = captureSink();
  const logger = createLogger({ sink }); // pas de level → info
  logger.debug("d");
  logger.info("i");
  assert.deepEqual(entries.map((e) => e.level), ["info"]);
});

test("LOG_LEVELS : priorités croissantes", () => {
  assert.ok(LOG_LEVELS.debug < LOG_LEVELS.info);
  assert.ok(LOG_LEVELS.info < LOG_LEVELS.warn);
  assert.ok(LOG_LEVELS.warn < LOG_LEVELS.error);
});

// --- Masquage des secrets (sécurité E7) ---

test("logger : masque les valeurs sensibles du contexte", () => {
  const { entries, sink } = captureSink();
  const logger = createLogger({ level: "debug", sink });

  logger.info("connexion", { user: "marie", token: "abc123", NOTION_TOKEN: "xyz" });

  const [entry] = entries;
  assert.equal(entry.user, "marie"); // non sensible → conservé
  assert.equal(entry.token, REDACTED);
  assert.equal(entry.NOTION_TOKEN, REDACTED); // inclusion insensible à la casse
});

test("logger : masque récursivement dans les objets imbriqués", () => {
  const { entries, sink } = captureSink();
  const logger = createLogger({ level: "debug", sink });

  logger.info("appel", { auth: { apiKey: "secret", scope: "read" } });

  const [entry] = entries;
  assert.equal(entry.auth.apiKey, REDACTED);
  assert.equal(entry.auth.scope, "read");
});

// --- Contexte de base et child ---

test("logger : le contexte de base est ajouté à chaque entrée", () => {
  const { entries, sink } = captureSink();
  const logger = createLogger({ level: "debug", sink, context: { service: "connector" } });
  logger.info("go");
  assert.equal(entries[0].service, "connector");
});

test("child : hérite de la config et enrichit le contexte", () => {
  const { entries, sink } = captureSink();
  const logger = createLogger({ level: "debug", sink, context: { service: "connector" } });
  const child = logger.child({ source: "apec" });

  child.warn("attention", { code: 1 });

  const [entry] = entries;
  assert.equal(entry.service, "connector"); // hérité
  assert.equal(entry.source, "apec"); // ajouté par child
  assert.equal(entry.code, 1);
  assert.equal(entry.level, "warn");
});

test("child : conserve le seuil du parent", () => {
  const { entries, sink } = captureSink();
  const logger = createLogger({ level: "warn", sink });
  const child = logger.child({ source: "apec" });
  assert.equal(child.info("i"), null); // toujours sous le seuil
  assert.ok(child.error("e"));
  assert.equal(entries.length, 1);
});

// --- Sortie par défaut ---

test("logger : sink par défaut route selon le niveau (console)", () => {
  const original = { log: console.log, warn: console.warn, error: console.error };
  const used = [];
  console.log = () => used.push("log");
  console.warn = () => used.push("warn");
  console.error = () => used.push("error");
  try {
    const logger = createLogger({ level: "debug" });
    logger.info("i");
    logger.warn("w");
    logger.error("e");
  } finally {
    Object.assign(console, original);
  }
  assert.deepEqual(used, ["log", "warn", "error"]);
});
