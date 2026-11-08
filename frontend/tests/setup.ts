import "@testing-library/jest-dom";
import { configure } from "@testing-library/react";

// Délai des attentes `findBy*` / `waitFor` : 3 s au lieu d'1 s. Sur une machine chargée (suite
// complète, build en parallèle), des rendus asynchrones ont dépassé 1 s (1,4 s et 1,9 s observés)
// et fait échouer des tests justes par ailleurs. Un test qui réussit n'attend pas plus longtemps.
configure({ asyncUtilTimeout: 3000 });
