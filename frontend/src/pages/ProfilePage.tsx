import { useTargetCandidate } from "../auth/useTargetCandidate";
import { ProfilePanel } from "../components/ProfilePanel";

/**
 * Page « Profil » dédiée : le CV, les compétences et le parcours sont du contenu de référence,
 * consulté et édité à part. Les sortir du cockpit (où ils étaient enfouis sous le flux d'activité)
 * leur donne un accès direct via la nav, et met l'import CV en évidence. Le cockpit n'en garde
 * qu'une carte résumé (cf. ProfileSummaryCard).
 */
export function ProfilePage() {
  const { target } = useTargetCandidate();

  return (
    <section className="space-y-6">
      <h2 className="text-xl font-semibold text-ink">Profil</h2>

      {target === "" ? (
        <p className="rounded-lg border border-dashed border-border bg-surface-raised p-6 text-center text-sm text-ink-muted">
          Aucune recherche pour le moment. Crée une recherche ci-dessus pour commencer.
        </p>
      ) : (
        <ProfilePanel key={target} candidateId={target} />
      )}
    </section>
  );
}
