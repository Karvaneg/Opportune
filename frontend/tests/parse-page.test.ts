import { describe, expect, it } from "vitest";
import { parsePage } from "../src/lib/parsePage";

describe("parsePage (OPP-240)", () => {
  it.each([
    [null, 1],
    ["2", 2],
    ["0", 1],
    ["-3", 1],
    ["2.0", 1],
    ["1e21", 1],
    ["abc", 1],
    ["99999999999999999999", 1],
  ])("?page=%s → page %i", (raw, expectedPage) => {
    expect(parsePage(raw)).toBe(expectedPage);
  });
});
