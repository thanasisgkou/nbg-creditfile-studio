import { describe, expect, it } from "vitest";
import { canonicalMoney } from "./api";

describe("Greek amount entry", () => {
  it("preserves sign and converts grouping and decimals without float arithmetic", () => {
    expect(canonicalMoney("-750.000,01 €")).toBe("-750000.01");
    expect(canonicalMoney("750000.01")).toBe("750000.01");
    expect(canonicalMoney("750.000")).toBe("750000");
  });
  it("rejects ambiguous foreign formatting and malformed amounts", () => {
    expect(() => canonicalMoney("750,000.01")).toThrow();
    expect(() => canonicalMoney("12.34.56")).toThrow();
    expect(() => canonicalMoney("")).toThrow();
  });
});
