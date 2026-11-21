import { describe, it, expect } from "vitest";
import { formatMoney, numericInput } from "../utils.js";

/**
 * Money crosses the wire as an exact decimal STRING ("19.99"), not a JSON
 * number, because a JSON number is read back as an IEEE-754 double and would
 * undo the exactness the backend works to preserve. These tests pin the two
 * places the frontend touches that contract.
 */
describe("formatMoney with decimal strings", () => {
  it("formats a decimal string exactly", () => {
    expect(formatMoney("1234.56", "USD")).toBe("$1,234.56");
    expect(formatMoney("0.10", "USD")).toBe("$0.10");
    expect(formatMoney("0.00", "USD")).toBe("$0.00");
  });

  it("keeps precision a float would lose", () => {
    // Beyond 2^53 a double cannot represent consecutive integers, let alone
    // the cents. Intl.NumberFormat accepts the decimal string and formats it
    // exactly (Intl NumberFormat V3), which is why money crosses the wire as
    // a string.
    const exact = "9007199254740993.01";
    expect(formatMoney(exact, "USD")).toBe("$9,007,199,254,740,993.01");
    // The same value through a float loses the cents AND the last digit.
    expect(formatMoney(Number(exact), "USD")).toBe("$9,007,199,254,740,994.00");

    // A mid-range amount formats identically either way, which is precisely
    // why this class of bug survives casual testing.
    expect(formatMoney("1234.56", "USD")).toBe(formatMoney(1234.56, "USD"));
  });

  it("still handles numbers, for anything not yet migrated", () => {
    expect(formatMoney(1234.56, "USD")).toBe("$1,234.56");
  });

  it("renders a dash for a missing amount, but not for zero", () => {
    expect(formatMoney(null, "USD")).toBe("—");
    expect(formatMoney(undefined, "USD")).toBe("—");
    expect(formatMoney("0.00", "USD")).toBe("$0.00");
  });

  it("respects the document's own currency", () => {
    expect(formatMoney("1000.00", "EUR")).toContain("1,000.00");
    expect(formatMoney("1000.00", "NGN")).toContain("1,000.00");
  });

  it("falls back rather than throwing on a bad currency code", () => {
    expect(() => formatMoney("10.00", "NOT_A_CURRENCY")).not.toThrow();
  });
});

describe("numericInput", () => {
  it("keeps what the user typed, without going through a float", () => {
    // Number("0.07") is 0.07000000000000001 at full precision; passing the
    // string through lets the backend parse it with Decimal.
    expect(numericInput("0.07")).toBe("0.07");
    expect(numericInput("1234.56")).toBe("1234.56");
    expect(numericInput("19.99")).toBe("19.99");
  });

  it("treats an empty field as absent", () => {
    expect(numericInput("")).toBeNull();
    expect(numericInput("   ")).toBeNull();
    expect(numericInput(null)).toBeNull();
    expect(numericInput(undefined)).toBeNull();
  });

  it("trims but does not otherwise rewrite the value", () => {
    expect(numericInput("  42.50  ")).toBe("42.50");
    // Validation is the server's job: it is the only place that can report a
    // bad value properly, so a nonsense entry is passed through untouched.
    expect(numericInput("abc")).toBe("abc");
  });

  it("never returns a number", () => {
    expect(typeof numericInput("10")).toBe("string");
  });
});
