import { describe, expect, it } from "vitest";
import { claimParts } from "./chatLinks";
import type { Source } from "./api";
const source = {
  document_id: "a",
  page: 1,
  block_id: "b1",
  quote: "Καθαρό αποτέλεσμα: (125.000) EUR",
} as Source;

describe("claim text integrity", () => {
  it.each([
    "125.000 EUR",
    "-125.000 EUR",
    "125.000,50 EUR",
    "4.580.000 EUR",
    "125000.00 EUR",
    "125,000.50 EUR",
    "(125.000) EUR",
    "−125.000 EUR",
    "125 000 EUR",
    "125.000 € και 125,50 EUR",
    '"125.000 €"',
  ])("preserves %s verbatim", (amount) => {
    const text = `Το ποσό είναι ${amount}.`;
    const parts = claimParts(text, [source]);
    expect(parts.map((p) => p.text).join("")).toBe(text);
    expect(parts.every((p) => !p.sources.length)).toBe(true);
  });
  it("does not infer provenance from sign or same-page amount matches", () => {
    const sources = [
      source,
      { ...source, block_id: "b2", quote: "Έσοδα: 125.000 EUR" },
    ];
    expect(claimParts("125.000,00 €", sources)).toEqual([
      { text: "125.000,00 €", sources: [] },
    ]);
  });
  it("preserves short quoted titles and offers all matching sources", () => {
    const title = "Στοιχεία Αιτούμενης Χρηματοδότησης";
    const text = `Δείτε «${title}» και «${title}».`;
    const sources = [
      { ...source, quote: title },
      { ...source, block_id: "b2", quote: title },
    ];
    const parts = claimParts(text, sources);
    expect(parts.map((p) => p.text).join("")).toBe(text);
    expect(parts.filter((p) => p.sources.length)).toEqual([
      { text: title, sources },
    ]);
  });
});
