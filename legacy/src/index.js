const { getTickets } = require("./notion");
const { formatTickets } = require("./display");
const {
  recommendNextTicket,
  getUrgentTickets,
  suggestPriority,
  explainRecommendation,
} = require("./services");

async function main() {
  try {
    const tickets = await getTickets();

    // 1. Prochain ticket recommandé.
    const recommendation = recommendNextTicket(tickets);
    console.log("🎯 Prochain ticket recommandé :");
    console.log("   " + explainRecommendation(recommendation));
    if (recommendation) console.log("   " + recommendation.id + " — " + recommendation.titre);

    // 2. Tickets urgents.
    const urgents = getUrgentTickets(tickets);
    console.log(`\n🔥 ${urgents.length} ticket(s) urgent(s) (score ≥ 5)`);
    console.log(formatTickets(urgents, { titre: "Urgents" }));

    // 3. Priorité suggérée pour les tickets sans priorité.
    const sansPriorite = tickets.filter((t) => !t.priorite);
    if (sansPriorite.length) {
      console.log(`\n🧭 Priorité suggérée pour ${sansPriorite.length} ticket(s) non priorisé(s) :`);
      for (const t of sansPriorite) {
        console.log(`   ${suggestPriority(t)} ← ${t.id || "(sans id)"} — ${t.titre || "—"}`);
      }
    }
  } catch (error) {
    console.error("❌ Erreur :", error.body || error.message);
  }
}

main();
