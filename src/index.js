const { getTickets } = require("./notion");
const { formatTickets } = require("./display");

async function main() {
  try {
    const tickets = await getTickets({ statut: "Backlog", phase: "MVP" });
    tickets.sort((a, b) => (a.priorite ?? "").localeCompare(b.priorite ?? ""));

    console.log(formatTickets(tickets, { titre: "Backlog / MVP" }));
  } catch (error) {
    console.error("❌ Erreur :", error.body || error.message);
  }
}

main();
