const { test } = require("node:test");
const assert = require("node:assert/strict");

const { toTicket, read, write } = require("./mappers");

// Fabrique une page Notion factice à partir de valeurs simples.
function fakePage(props = {}) {
  return {
    id: "page-123",
    url: "https://notion.so/page-123",
    properties: {
      ID: { title: [{ plain_text: props.id ?? "" }] },
      Titre: { rich_text: [{ plain_text: props.titre ?? "" }] },
      Statut: { status: props.statut ? { name: props.statut } : null },
      Priorité: { select: props.priorite ? { name: props.priorite } : null },
      Type: { select: props.type ? { name: props.type } : null },
      Phase: { select: props.phase ? { name: props.phase } : null },
      Epic: { select: props.epic ? { name: props.epic } : null },
      Estimation: { select: props.estimation ? { name: props.estimation } : null },
    },
  };
}

test("toTicket mappe tous les champs + url et pageId", () => {
  const page = fakePage({
    id: "OPP-010",
    titre: "Créer le modèle de profil candidat",
    statut: "Backlog",
    priorite: "P0",
    type: "Feature",
    phase: "MVP",
    epic: "Epic E1 — Profil candidat",
    estimation: "3",
  });

  assert.deepEqual(toTicket(page), {
    url: "https://notion.so/page-123",
    pageId: "page-123",
    id: "OPP-010",
    titre: "Créer le modèle de profil candidat",
    statut: "Backlog",
    priorite: "P0",
    type: "Feature",
    phase: "MVP",
    epic: "Epic E1 — Profil candidat",
    estimation: "3",
  });
});

test("toTicket : propriétés select vides → null", () => {
  const ticket = toTicket(fakePage({ id: "OPP-011" }));
  assert.equal(ticket.priorite, null);
  assert.equal(ticket.epic, null);
  assert.equal(ticket.estimation, null);
});

test("toTicket : texte absent → chaîne vide", () => {
  const ticket = toTicket(fakePage({}));
  assert.equal(ticket.id, "");
  assert.equal(ticket.titre, "");
});

test("read.text concatène les segments de rich text", () => {
  const prop = { rich_text: [{ plain_text: "Ver" }, { plain_text: "sion" }] };
  assert.equal(read.text(prop), "Version");
});

test("write produit le format Notion attendu", () => {
  assert.deepEqual(write.status("Done"), { status: { name: "Done" } });
  assert.deepEqual(write.select("P1"), { select: { name: "P1" } });
});
