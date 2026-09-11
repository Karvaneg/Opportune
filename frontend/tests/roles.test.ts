import { describe, expect, it } from "vitest";
import { isReviewer } from "../src/auth/roles";
import type { Me } from "../src/api/types";

const me = (role: string | null): Me => ({
  id: "u",
  role,
  owned_count: 0,
  owned_candidate_ids: [],
});

describe("isReviewer (garde reviewer UI — OPP-106)", () => {
  it("vrai pour le rôle reviewer", () => {
    expect(isReviewer(me("reviewer"))).toBe(true);
  });

  it("faux pour un autre rôle", () => {
    expect(isReviewer(me("candidate"))).toBe(false);
  });

  it("faux si rôle absent ou identité nulle", () => {
    expect(isReviewer(me(null))).toBe(false);
    expect(isReviewer(null)).toBe(false);
  });
});
