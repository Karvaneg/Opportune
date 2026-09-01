const { test } = require("node:test");
const assert = require("node:assert/strict");

const notion = require("./client");
const { getTickets } = require("./tickets");

// Page Notion factice minimale (toTicket tolère les propriétés absentes).
function fakePage({ id = "", statut = null } = {}) {
  return {
    id: "pg-" + id,
    url: "https://notion.so/" + id,
    properties: {
      ID: { title: [{ plain_text: id }] },
      Statut: { status: statut ? { name: statut } : null },
    },
  };
}

test("getTickets : applique le filtre construit et normalise les pages", async (t) => {
  const query = t.mock.method(notion.dataSources, "query", async () => ({
    results: [fakePage({ id: "OPP-001", statut: "Backlog" })],
    has_more: false,
  }));

  const tickets = await getTickets({ statut: "Backlog" });

  assert.equal(query.mock.callCount(), 1);
  const arg = query.mock.calls[0].arguments[0];
  assert.deepEqual(arg.filter, {
    and: [{ property: "Statut", status: { equals: "Backlog" } }],
  });
  assert.equal(tickets.length, 1);
  assert.equal(tickets[0].id, "OPP-001");
  assert.equal(tickets[0].statut, "Backlog");
  assert.equal(tickets[0].pageId, "pg-OPP-001");
});

test("getTickets : sans filtre → filter undefined", async (t) => {
  const query = t.mock.method(notion.dataSources, "query", async () => ({
    results: [],
    has_more: false,
  }));

  await getTickets();
  assert.equal(query.mock.calls[0].arguments[0].filter, undefined);
});

test("getTickets : enchaîne la pagination via next_cursor", async (t) => {
  const query = t.mock.method(notion.dataSources, "query", async ({ start_cursor }) => {
    if (!start_cursor) {
      return { results: [fakePage({ id: "A" })], has_more: true, next_cursor: "cur-2" };
    }
    return { results: [fakePage({ id: "B" })], has_more: false };
  });

  const tickets = await getTickets();

  assert.equal(query.mock.callCount(), 2);
  assert.equal(query.mock.calls[1].arguments[0].start_cursor, "cur-2");
  assert.deepEqual(tickets.map((t) => t.id), ["A", "B"]);
});

test("getTickets : aucun résultat → tableau vide", async (t) => {
  t.mock.method(notion.dataSources, "query", async () => ({ results: [], has_more: false }));
  assert.deepEqual(await getTickets({ statut: "Done" }), []);
});
