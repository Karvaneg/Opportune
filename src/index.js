const { getTickets } = require("./notion");
const { recommendNextTicket, explainRecommendation } = require("./services/opportuneService");

async function main() {
  try {
    const tickets = await getTickets();
    const recommendation = recommendNextTicket(tickets);

    console.log("Prochain ticket recommandé :");
    if (recommendation) {
      console.table([
        {
          id: recommendation.id,
          titre: recommendation.titre,
          priorité: recommendation.priorite,
          statut: recommendation.statut,
          score: recommendation.score,
        },
      ]);
    }
    console.log(explainRecommendation(recommendation));
  } catch (error) {
    console.error("❌ Erreur :", error.body || error.message);
  }
}

main();
