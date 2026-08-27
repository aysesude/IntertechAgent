import { describe, expect, it } from "vitest";
import { computePerformanceStats } from "./mockData";
import type { PerformanceRange } from "@/types/finance";

/**
 * computePerformanceStats — Dashboard'daki Performans grafiğinin istatistik
 * kutularını besliyor (bkz. PerformanceChart.tsx). Boş/sıfır portföy
 * senaryolarında "NaN%" üretmemesi (AK 5.5 — uydurmama) test ediliyor.
 */

function range(ustuneYaz: Partial<PerformanceRange> = {}): PerformanceRange {
  return {
    key: "1A",
    subtitle: "Son 1 ay",
    points: [
      { label: "1 Oca", portfolio: 100_000, invested: 90_000 },
      { label: "15 Oca", portfolio: 110_000, invested: 90_000 },
    ],
    annotationIndex: null,
    returnPct: null,
    ...ustuneYaz,
  };
}

describe("computePerformanceStats", () => {
  it("boş seride (points===[]) high/low/profit 0, returnPct null döner — NaN/±Infinity üretmez", () => {
    const stats = computePerformanceStats(range({ points: [] }));
    expect(stats).toEqual({ high: 0, low: 0, returnPct: null, profit: 0 });
  });

  it("ilk nokta 0 ve backend TWR'si yoksa returnPct null döner (0/0 = NaN yerine)", () => {
    const stats = computePerformanceStats(
      range({
        points: [
          { label: "1 Oca", portfolio: 0, invested: 0 },
          { label: "15 Oca", portfolio: 50_000, invested: 45_000 },
        ],
        returnPct: null,
      }),
    );
    expect(stats.returnPct).toBeNull();
    expect(Number.isNaN(stats.returnPct)).toBe(false);
  });

  it("backend TWR'si (returnPct) verilmişse ham hesaplama yerine onu kullanır", () => {
    const stats = computePerformanceStats(range({ returnPct: 12.5 }));
    expect(stats.returnPct).toBe(12.5);
  });

  it("normal seride high/low/returnPct/profit doğru hesaplanır", () => {
    const stats = computePerformanceStats(range());
    expect(stats.high).toBe(110_000);
    expect(stats.low).toBe(100_000);
    expect(stats.returnPct).toBe(10);
    expect(stats.profit).toBe(20_000);
  });
});
