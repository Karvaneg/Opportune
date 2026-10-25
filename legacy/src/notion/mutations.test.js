const { test } = require("node:test");
const assert = require("node:assert/strict");

const notion = require("./client");
const { updateTicketStatus } = require("./mutations");

test("updateTicketStatus : appelle pages.update avec le bon id et le format status", async (t) => {
  const update = t.mock.method(notion.pages, "update", async ({ page_id, properties }) => ({
    id: page_id,
    url: "https://notion.so/" + page_id,
    properties: {
      ID: { title: [{ plain_text: "OPP-010" }] },
      Statut: { status: properties.Statut.status }, // renvoie le statut appliqué
    },
  }));

  const ticket = await updateTicketStatus("pg-1", "In Progress");

  assert.equal(update.mock.callCount(), 1);
  const arg = update.mock.calls[0].arguments[0];
  assert.equal(arg.page_id, "pg-1");
  assert.deepEqual(arg.properties, { Statut: { status: { name: "In Progress" } } });
});

test("updateTicketStatus : renvoie le ticket normalisé après mise à jour", async (t) => {
  t.mock.method(notion.pages, "update", async ({ page_id, properties }) => ({
    id: page_id,
    url: "https://notion.so/" + page_id,
    properties: {
      ID: { title: [{ plain_text: "OPP-010" }] },
      Statut: { status: properties.Statut.status },
    },
  }));

  const ticket = await updateTicketStatus("pg-1", "Done");
  assert.equal(ticket.id, "OPP-010");
  assert.equal(ticket.statut, "Done");
  assert.equal(ticket.pageId, "pg-1");
});
