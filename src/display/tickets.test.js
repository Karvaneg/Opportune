const { test } = require("node:test");
const assert = require("node:assert/strict");

const { formatTickets, formatTicket } = require("./tickets");

const ticketBase = {
  id: "OPP-010",
  titre: "Créer le modèle de profil candidat",
  priorite: "P0",
  epic: "Epic E1 — Profil candidat",
  estimation: "3",
};

test("liste vide → message dédié avec le titre", () => {
  assert.equal(formatTickets([], { titre: "Backlog / MVP" }), "Aucun ticket · Backlog / MVP");
});

test("en-tête : compte et titre", () => {
  const sortie = formatTickets([ticketBase], { titre: "Backlog / MVP" });
  assert.match(sortie, /1 ticket\(s\) · Backlog \/ MVP/);
});

test("une ligne contient priorité, id, titre et meta", () => {
  const ligne = formatTicket(ticketBase);
  assert.match(ligne, /P0/);
  assert.match(ligne, /OPP-010/);
  assert.match(ligne, /Créer le modèle de profil candidat/);
  assert.match(ligne, /Epic E1 — Profil candidat · est\. 3/);
});

test("valeurs manquantes → tiret cadratin", () => {
  const ligne = formatTicket({ id: "OPP-099", titre: "X" });
  assert.match(ligne, /est\. —/);
});
