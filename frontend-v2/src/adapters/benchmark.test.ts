import { describe, expect, it } from "vitest";
import type { ApiBenchmarkComparison } from "@/api/portfolio";
import { benchmarkUyarisi, toBenchmarkBars } from "./benchmark";

function kiyas(ustuneYaz: Partial<ApiBenchmarkComparison> = {}): ApiBenchmarkComparison {
  return {
    user_id: "u1",
    window: "12m",
    start_date: "2025-09-08",
    end_date: "2026-08-26",
    truncated_to_inception: false,
    portfolio_return_percent: 91.7,
    benchmarks: [
      { symbol: "XU100", name: "BIST 100 Endeksi", return_percent: 39.8 },
      { symbol: "USDTRY", name: "Amerikan Doları", return_percent: 16.8 },
      { symbol: "EURTRY", name: "Euro", return_percent: 16.6 },
      { symbol: "XAUTRY", name: "Gram Altın", return_percent: 49.0 },
    ],
    excluded_symbols: [],
    ...ustuneYaz,
  };
}

describe("toBenchmarkBars", () => {
  it("beş çubuk üretir: portföy + dört kıyas", () => {
    const bars = toBenchmarkBars(kiyas());

    expect(bars.map((b) => b.id)).toEqual(["portfoy", "XU100", "USDTRY", "EURTRY", "XAUTRY"]);
    expect(bars.map((b) => b.returnPct)).toEqual([91.7, 39.8, 16.8, 16.6, 49.0]);
  });

  it("backend sırasını KORUR", () => {
    // Dönem değişince çubukların yer değiştirmesi karşılaştırmayı okunmaz
    // yapar; sıralama (ör. getiriye göre) bilerek yapılmıyor.
    const tersi = kiyas({
      benchmarks: [
        { symbol: "XAUTRY", name: "Gram Altın", return_percent: 49.0 },
        { symbol: "XU100", name: "BIST 100 Endeksi", return_percent: 39.8 },
        { symbol: "USDTRY", name: "Amerikan Doları", return_percent: 16.8 },
        { symbol: "EURTRY", name: "Euro", return_percent: 16.6 },
      ],
    });

    expect(toBenchmarkBars(tersi).map((b) => b.id)).toEqual([
      "portfoy",
      "XAUTRY",
      "XU100",
      "USDTRY",
      "EURTRY",
    ]);
  });

  it("uzun unvan yerine kısa etiket kullanır", () => {
    // Çubuk altında yan yana beş uzun ad sığmıyor.
    const bars = toBenchmarkBars(kiyas());
    expect(bars.map((b) => b.label)).toEqual(["Portföyüm", "BIST100", "USD", "EUR", "Altın"]);
  });

  it("tanınmayan sembolü DÜŞÜRMEZ, adıyla gösterir", () => {
    // Sessizce elemek, kullanıcının eksik bir kıyas gördüğünü fark etmemesi
    // demek olurdu.
    const bars = toBenchmarkBars(
      kiyas({ benchmarks: [{ symbol: "GBPTRY", name: "İngiliz Sterlini", return_percent: 5 }] }),
    );
    expect(bars.map((b) => b.label)).toEqual(["Portföyüm", "İngiliz Sterlini"]);
  });

  it("hesaplanamayan getiriyi null taşır, 0 ÜRETMEZ", () => {
    // 0 gösterilseydi "bu dönemde hiç kazandırmadı" diye okunurdu; oysa
    // elimizde bilgi yok (AK 5.5).
    const bars = toBenchmarkBars(
      kiyas({
        portfolio_return_percent: null,
        benchmarks: [{ symbol: "XU100", name: "BIST 100", return_percent: null }],
      }),
    );
    expect(bars.map((b) => b.returnPct)).toEqual([null, null]);
  });

  it("portföy çubuğu diğerlerinden FARKLI renkte", () => {
    const [portfoy, ...digerleri] = toBenchmarkBars(kiyas());
    expect(digerleri.every((b) => b.color !== portfoy.color)).toBe(true);
    // Kıyas enstrümanları kendi aralarında aynı tonda.
    expect(new Set(digerleri.map((b) => b.color)).size).toBe(1);
  });
});

describe("benchmarkUyarisi", () => {
  it("uyarı yoksa null", () => {
    expect(benchmarkUyarisi(kiyas())).toBeNull();
  });

  it("kırpılmış pencereyi söyler", () => {
    // "Yıllık" yazıp dört aylık getiri göstermek kıyası olduğundan iyi ya da
    // kötü gösterir; sessiz kalınamaz.
    const uyari = benchmarkUyarisi(kiyas({ truncated_to_inception: true }));
    expect(uyari).toContain("2025-09-08");
  });

  it("hesaba katılmayan varlıkları söyler", () => {
    const uyari = benchmarkUyarisi(kiyas({ excluded_symbols: ["BHE", "AAPL"] }));
    expect(uyari).toContain("BHE");
    expect(uyari).toContain("AAPL");
  });

  it("iki uyarıyı birleştirir", () => {
    const uyari = benchmarkUyarisi(
      kiyas({ truncated_to_inception: true, excluded_symbols: ["BHE"] }),
    );
    expect(uyari).toContain("2025-09-08");
    expect(uyari).toContain("BHE");
  });
});
