const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const {
  parseEnv,
  loadEnv,
  hasSecret,
  getSecret,
  requireSecrets,
  maskSecret,
} = require("./secrets");

function tmpFile(content) {
  const file = path.join(os.tmpdir(), `env-${process.hrtime.bigint()}`);
  fs.writeFileSync(file, content);
  return file;
}

// --- parseEnv ---

test("parseEnv : parse KEY=VALUE, ignore commentaires/vides, retire les guillemets", () => {
  const env = parseEnv(`
# commentaire
NOTION_TOKEN=abc123

DISCORD_TOKEN="secret avec espaces"
EMPTY_LINE_ABOVE='quoted'
`);
  assert.equal(env.NOTION_TOKEN, "abc123");
  assert.equal(env.DISCORD_TOKEN, "secret avec espaces");
  assert.equal(env.EMPTY_LINE_ABOVE, "quoted");
  assert.equal(Object.keys(env).length, 3);
});

// --- loadEnv ---

test("loadEnv : charge dans une source sans écraser, override si demandé", () => {
  const file = tmpFile("A=fromfile\nB=fromfile");
  try {
    const source = { A: "existant" };
    loadEnv(file, { source });
    assert.equal(source.A, "existant"); // non écrasé
    assert.equal(source.B, "fromfile");

    loadEnv(file, { source, override: true });
    assert.equal(source.A, "fromfile"); // écrasé
  } finally {
    fs.rmSync(file, { force: true });
  }
});

test("loadEnv : fichier inexistant → {} sans erreur", () => {
  assert.deepEqual(loadEnv(path.join(os.tmpdir(), "n-existe-pas-xyz")), {});
});

// --- getSecret / hasSecret / requireSecrets ---

test("getSecret : requis manquant → erreur ; optionnel → null", () => {
  const source = { TOKEN: "v" };
  assert.equal(getSecret("TOKEN", { source }), "v");
  assert.throws(() => getSecret("ABSENT", { source }), /manquante : ABSENT/);
  assert.equal(getSecret("ABSENT", { source, required: false }), null);
});

test("hasSecret : présent et non vide", () => {
  assert.equal(hasSecret("A", { A: "x" }), true);
  assert.equal(hasSecret("A", { A: "" }), false);
  assert.equal(hasSecret("A", {}), false);
});

test("requireSecrets : liste tous les manquants d'un coup", () => {
  assert.equal(requireSecrets(["A", "B"], { A: "x", B: "y" }), true);
  assert.throws(() => requireSecrets(["A", "B", "C"], { A: "x" }), /manquantes : B, C/);
});

// --- maskSecret ---

test("maskSecret : ne révèle jamais la valeur", () => {
  const masked = maskSecret("super-secret-token");
  assert.ok(!masked.includes("secret"));
  assert.equal(maskSecret(""), "(non défini)");
  assert.equal(maskSecret(undefined), "(non défini)");
});
