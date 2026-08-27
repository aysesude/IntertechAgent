import { describe, expect, it } from "vitest";
import type { ApiRiskAssessment } from "@/api/risk";
import type {
  ApiHoldingsValuation,
  ApiPerformanceResult,
  ApiPortfolioSummary,
  ApiTransactionList,
} from "@/api/portfolio";
import {
  priceFreshnessWarning,
  toRiskSummary,
  toAllocation,
  toDashboardData,
  toPerformanceRange,
  toSummary,
  toTransactions,
} from "./dashboard";

/**
 * Dashboard adapter testleri.
 *
 * Alan eşlemesi sessizce yanlış olabilecek bir yer: `total_cost_basis` ile
 * `net_invested` karıştırılırsa ekrandaki üç rakam birbirini tutmaz, `null`
 * gelen bir değer `0` olarak gösterilirse "bugün hiç değişmedi" gibi YANLIŞ
 * ama makul görünen bir cümle üretilir. Bunlar tarayıcıda fark edilmez;
 * rakam vardır ve doğru görünür.
 *
 * Beklenen değerler docs/API.md'deki örneklere bakılarak ELLE yazıldı,
 * adapter'ın kendi çıktısından türetilmedi.
 */

const OZET: ApiPortfolioSummary = {
  user_id: "u1",
  as_of: "2026-08-20",
  oldest_price_date: "2026-08-20",
  total_value: 2_681_069.66,
  total_cost_basis: 1_682_346.32,
  net_invested: 1_870_000,
  total_gain_loss: { amount: 811_069.66, percent: 43.37 },
  allocation: [
    { asset_class: "stock", value: 1_194_764.65, percent: 44.56 },
    { asset_class: "cash", value: 398_326.94, percent: 14.87 },
  ],
  holdings_count: 10,
};

function performans(ustuneYaz: Partial<ApiPerformanceResult["summary"]> = {}): ApiPerformanceResult {
  return {
    user_id: "u1",
    as_of: "2026-08-20",
    window: "3m",
    granularity: "daily",
    inception: "2025-08-05",
    truncated_to_inception: false,
    series: [
      { date: "2026-05-22", value_try: 1_410_924.92, invested_try: 1_460_000 },
      { date: "2026-08-20", value_try: 1_653_329.29, invested_try: 1_460_000 },
    ],
    summary: {
      start_value: 1_410_924.92,
      end_value: 1_653_329.29,
      change_amount: 242_404.37,
      change_percent: 17.18,
      realized_pnl: 0,
      unrealized_pnl: 179_532.29,
      changes: { daily: 2.21, weekly: 4.88, monthly: 10.05 },
      ...ustuneYaz,
    },
  };
}

describe("toSummary", () => {
  it("kâr/zararın tabanı olarak NET SERMAYEYİ taşır, maliyeti değil", () => {
    // İkisi karıştırılırsa ekrandaki üç rakam birbirini tutmaz: hesapta duran,
    // hiç yatırıma dönüşmemiş para kâr olarak raporlanır (docs/API.md).
    const s = toSummary(OZET, performans());
    expect(s.netInvested).toBe(1_870_000);
    expect(s.costBasis).toBe(1_682_346.32);
    expect(s.totalPL).toBe(811_069.66);
    // Toplam değer − net sermaye = kâr. Üçü birbirini tutmalı.
    expect(s.totalValue - s.netInvested).toBeCloseTo(s.totalPL, 2);
  });

  it("günlük değişimi yüzdeden TL'ye çevirir", () => {
    const s = toSummary(OZET, performans());
    expect(s.todayChangePct).toBe(2.21);
    // 2.681.069,66 × (0,0221 / 1,0221) ≈ 57.970,5
    //
    // Not: bu beklenti ilk yazıldığında 57.988 idi (yüzde doğrudan toplam
    // değerle çarpılmıştı). Doğrusu bugünkü değerden GERİYE çözmek: dünkü
    // değer = bugünkü / (1 + %değişim). Test, koddaki değil kendi
    // aritmetiğimdeki hatayı yakaladı.
    expect(s.todayChange).toBeCloseTo(57_970.5, 0);
  });

  it("günlük değişim hesaplanamıyorsa alanı HİÇ doldurmaz", () => {
    // Sıfır yazmak "bugün hiç değişmedi" demek olurdu — yanlış ama makul
    // görünen bir cümle (AK 5.5).
    const s = toSummary(OZET, performans({ changes: { daily: null, weekly: null, monthly: null } }));
    expect(s.todayChange).toBeUndefined();
    expect(s.todayChangePct).toBeUndefined();
  });

  it("dönem getirisi hesaplanamıyorsa alanı HİÇ doldurmaz", () => {
    const s = toSummary(OZET, performans({ change_percent: null }));
    expect(s.periodReturnPct).toBeUndefined();
  });

  it("kaynağı olmayan alanları üretmez", () => {
    // Risk skoru (v2'de kaldırıldı) ve reel getiri (enflasyon kaynağı yok)
    // uydurulmamalı.
    const s = toSummary(OZET, performans());
    expect(s.riskScore).toBeUndefined();
    expect(s.realReturnPct).toBeUndefined();
  });
});

describe("toPerformanceRange", () => {
  it("iki seriyi de taşır — boşluk kârı gösterir", () => {
    const r = toPerformanceRange(performans(), "3A");
    expect(r.points).toHaveLength(2);
    expect(r.points[0]).toMatchObject({ portfolio: 1_410_924.92, invested: 1_460_000 });
    // İlk noktada yatırılan > değer: portföy o gün zarardaydı. Adapter bunu
    // düzeltmemeli, olduğu gibi taşımalı.
    expect(r.points[0].invested).toBeGreaterThan(r.points[0].portfolio);
  });

  it("TWR'yi seriden TÜRETMEZ, backend'den taşır", () => {
    // Ham değer farkından hesaplansaydı dönem içinde yatırılan para getiri
    // gibi görünürdü.
    const r = toPerformanceRange(performans(), "3A");
    expect(r.returnPct).toBe(17.18);
  });

  it("kırpılmış pencereyi işaretler", () => {
    const sonuc = performans();
    sonuc.truncated_to_inception = true;
    expect(toPerformanceRange(sonuc, "1Y").truncatedToInception).toBe(true);
  });

  it("1Y'de ay etiketi, kısa dönemde gün+ay etiketi kullanır", () => {
    expect(toPerformanceRange(performans(), "1Y").points[0].label).toBe("May 26");
    expect(toPerformanceRange(performans(), "3A").points[0].label).toBe("22 May");
  });
});

describe("toAllocation", () => {
  const varliklar: ApiHoldingsValuation = {
    user_id: "u1",
    as_of: "2026-08-20",
    holdings: [
      {
        symbol: "TUPRS",
        name: "Tüpraş",
        asset_class: "stock",
        currency: "TRY",
        quantity: 1428,
        current_price_try: 391.75,
        market_value_try: 559_419,
        weight_percent: 20.86,
        avg_cost_try: 172.63,
        cost_basis_try: 246_515.64,
        unrealized_pnl_try: 312_903.36,
        unrealized_pnl_percent: 126.91,
        realized_pnl_try: 0,
        price_missing: false,
      },
      {
        symbol: "YOKFIYAT",
        name: "Fiyatı Bilinmeyen",
        asset_class: "stock",
        currency: "TRY",
        quantity: 10,
        current_price_try: null,
        market_value_try: null,
        weight_percent: null,
        avg_cost_try: 100,
        cost_basis_try: 1000,
        unrealized_pnl_try: null,
        unrealized_pnl_percent: null,
        realized_pnl_try: 0,
        price_missing: true,
      },
    ],
    best_performer: { symbol: "TUPRS", name: "Tüpraş", unrealized_pnl_percent: 126.91 },
    worst_performer: { symbol: "SASA", name: "Sasa Polyester", unrealized_pnl_percent: -82.67 },
    excluded_symbols: [],
  };

  it("varlık sınıflarını arayüz kimliklerine eşler", () => {
    const dilimler = toAllocation(OZET, varliklar, false);
    expect(dilimler.map((d) => d.id)).toEqual(["stocks", "cash"]);
    expect(dilimler[0].name).toBe("Hisse Senedi");
  });

  it("fiyatı bulunamayan varlığı alt kırılıma KOYMAZ", () => {
    // Değeri `null` olan satırı yüzdeye çevirmek yanlış sayı üretirdi.
    const hisse = toAllocation(OZET, varliklar, false)[0];
    expect(hisse.subcategories.map((a) => a.name)).toEqual(["Tüpraş"]);
  });

  it("varlık tablosu gelmezse dağılımı alt kırılımsız çizer", () => {
    // Kısmi başarısızlıkta ekranın tamamını karartmıyoruz.
    const dilimler = toAllocation(OZET, null, false);
    expect(dilimler).toHaveLength(2);
    expect(dilimler[0].subcategories).toEqual([]);
  });

  it("crypto ÜRETMEZ — backend'de böyle bir sınıf yok", () => {
    const dilimler = toAllocation(OZET, varliklar, false);
    expect(dilimler.some((d) => d.id === "crypto")).toBe(false);
  });

  it("temaya göre farklı palet kullanır", () => {
    const acik = toAllocation(OZET, varliklar, false)[0].color;
    const koyu = toAllocation(OZET, varliklar, true)[0].color;
    expect(acik).not.toBe(koyu);
  });
});

describe("toTransactions", () => {
  const liste: ApiTransactionList = {
    user_id: "u1",
    start_date: null,
    end_date: null,
    transactions: [
      {
        transaction_date: "2025-09-08T10:00:00Z",
        type: "deposit",
        symbol: null,
        quantity: 0,
        price: null,
        currency: "TRY",
        fx_rate_to_try: 1,
        fee_try: 0,
        cash_amount_try: 500_000,
        position_after: null,
      },
      {
        transaction_date: "2025-09-10T10:00:00Z",
        type: "buy",
        symbol: "TUPRS",
        quantity: 467,
        price: 175.88,
        currency: "TRY",
        fx_rate_to_try: 1,
        fee_try: 82.13,
        cash_amount_try: -82_134.81,
        position_after: 467,
      },
    ],
  };

  it("en yeni işlemi başa alır", () => {
    // Backend defter sırasında (eskiden yeniye) döndürüyor.
    const islemler = toTransactions(liste);
    expect(islemler[0].title).toContain("TUPRS");
    expect(islemler[1].title).toBe("Para Yatırma");
  });

  it("yönü nakit akışının İŞARETİNDEN belirler", () => {
    const islemler = toTransactions(liste);
    expect(islemler[0].direction).toBe("out"); // alım: para çıktı
    expect(islemler[1].direction).toBe("in"); // yatırma: para girdi
  });

  it("nakit hareketinde miktar ayrıntısı göstermez", () => {
    // Faiz/yatırma satırlarında "0,00 adet" yazması bilinen bir kusurdu.
    const islemler = toTransactions(liste);
    expect(islemler[1].detail).toBe("");
  });

  it("limitten fazlasını kesip en yenileri bırakır", () => {
    expect(toTransactions(liste, 1)).toHaveLength(1);
    expect(toTransactions(liste, 1)[0].title).toContain("TUPRS");
  });
});

describe("priceFreshnessWarning", () => {
  it("tüm fiyatlar aynı gündense uyarı üretmez", () => {
    expect(priceFreshnessWarning(OZET)).toBeNull();
  });

  it("fiyatların bir kısmı eskiyse UYARIR", () => {
    // docs/API.md bunu şart koşuyor: yalnızca as_of gösterilirse özet
    // olduğundan taze görünür.
    const eski = { ...OZET, oldest_price_date: "2026-08-12" };
    expect(priceFreshnessWarning(eski)).toContain("12/08/2026");
  });

  it("hiç fiyatlı varlık yoksa uyarı üretmez", () => {
    expect(priceFreshnessWarning({ ...OZET, oldest_price_date: null })).toBeNull();
  });
});

describe("toDashboardData", () => {
  it("kaynağı olmayan önerileri üretmez", () => {
    const d = toDashboardData({
      summary: OZET,
      performance: performans(),
      range: "3A",
      holdings: null,
      transactions: null,
      risk: null,
      darkTheme: false,
    });
    // Yeniden dengeleme önerileri risk ajanından gelecek; uydurulmuyor.
    expect(d.recommendations).toEqual([]);
    expect(d.bestPerformer).toBeUndefined();
  });

  it("yalnızca SEÇİLİ dönemi doldurur", () => {
    const d = toDashboardData({
      summary: OZET,
      performance: performans(),
      range: "3A",
      holdings: null,
      transactions: null,
      risk: null,
      darkTheme: false,
    });
    expect(d.performance["3A"]).toBeDefined();
    expect(d.performance["1Y"]).toBeUndefined();
  });

  it("sayımları özetten alır", () => {
    const d = toDashboardData({
      summary: OZET,
      performance: performans(),
      range: "3A",
      holdings: null,
      transactions: null,
      risk: null,
      darkTheme: false,
    });
    expect(d.instrumentCount).toBe(10);
    expect(d.assetClassCount).toBe(2);
    // Uygulamanın ortak tarih biçimi gün/ay/yıl (bkz. utils/format.ts).
    expect(d.lastUpdated).toBe("20/08/2026");
  });
});

// ---------------------------------------------------------------------------
// Risk
// ---------------------------------------------------------------------------

function risk(ustuneYaz: Partial<ApiRiskAssessment> = {}): ApiRiskAssessment {
  return {
    user_id: "u1",
    as_of: "2026-08-20",
    risk_profile: "conservative",
    risk_profile_source: "user",
    risk_survey_score: 2,
    total_value: 1_569_468.64,
    risk_level: "medium_high",
    is_within_profile: false,
    metrics: {
      annualized_volatility_percent: 24.31,
      max_drawdown_percent: 8.4,
      category_metrics: [],
      asset_metrics: [],
      diversification_ratio: 1.36,
      value_at_risk_try: 6968,
      value_at_risk_percent: 0.44,
      value_at_risk_confidence: 95,
      value_at_risk_horizon_days: 1,
      sharpe_ratio: -6.74,
      risk_free_rate_percent: 37,
      risk_free_rate_is_live: false,
      max_asset_weight_percent: 24.17,
      max_asset_symbol: "PPF",
      max_class_weight_percent: 54.77,
      max_class: "cash",
      herfindahl_index: 0.1646,
      holdings_count: 8,
      asset_class_count: 5,
      price_points_used: 260,
    },
    warnings: [],
    disclaimer: "Bu bir yatırım tavsiyesi değildir.",
    ...ustuneYaz,
  };
}

describe("toRiskSummary", () => {
  it("7 kademeli etiketi Türkçeye çevirir", () => {
    // 0-100 kompozit skor v2'de KALDIRILDI; etiket tek gösterim.
    expect(toRiskSummary(risk()).levelLabel).toBe("Orta-Yüksek");
    expect(toRiskSummary(risk({ risk_level: "very_low" })).levelLabel).toBe("Çok Düşük");
    expect(toRiskSummary(risk({ risk_level: "very_high" })).levelLabel).toBe("Çok Yüksek");
  });

  it("etiketin SAYISAL karşılığını da taşır", () => {
    // Gösterge (RiskLevelBar) sıra bilgisine ihtiyaç duyuyor. Etiketten
    // yeniden çıkarmak, çeviri değişince sessizce kırılırdı.
    expect(toRiskSummary(risk({ risk_level: "very_low" })).level).toBe(1);
    expect(toRiskSummary(risk({ risk_level: "medium_high" })).level).toBe(5);
    expect(toRiskSummary(risk({ risk_level: "very_high" })).level).toBe(7);
    expect(toRiskSummary(risk({ risk_level: null })).level).toBeNull();
  });

  it("etiket ile sıra AYNI kademeyi gösterir", () => {
    // İki tablo yan yana elle tutuluyor; ayrıştıklarında gösterge doğru
    // metnin yanına yanlış rengi koyar ve bunu kimse fark etmez.
    const seviyeler = [
      ["very_low", 1, "Çok Düşük"],
      ["low", 2, "Düşük"],
      ["low_medium", 3, "Düşük-Orta"],
      ["medium", 4, "Orta"],
      ["medium_high", 5, "Orta-Yüksek"],
      ["high", 6, "Yüksek"],
      ["very_high", 7, "Çok Yüksek"],
    ] as const;

    for (const [apiDeger, sira, etiket] of seviyeler) {
      const ozet = toRiskSummary(risk({ risk_level: apiDeger }));
      expect(ozet.level).toBe(sira);
      expect(ozet.levelLabel).toBe(etiket);
    }
  });

  it("profil bandının dışında olmayı taşır", () => {
    expect(toRiskSummary(risk()).withinProfile).toBe(false);
    expect(toRiskSummary(risk({ is_within_profile: true })).withinProfile).toBe(true);
  });

  it("hesaplanamayan risk için null taşır, 0 ÜRETMEZ", () => {
    // 0 gösterilseydi ekranda "riskiniz yok" yazardı — elimizde olmayan bir
    // bilgiyi uydurmak olurdu (AK 2.7 / 5.5).
    const yetersiz = toRiskSummary(
      risk({
        risk_level: null,
        is_within_profile: null,
        metrics: { ...risk().metrics, annualized_volatility_percent: null },
        warnings: ["Yeterli fiyat geçmişi yok."],
      }),
    );
    expect(yetersiz.levelLabel).toBeNull();
    expect(yetersiz.annualizedVolatilityPct).toBeNull();
    expect(yetersiz.warning).toBe("Yeterli fiyat geçmişi yok.");
  });

  it("anket puanını taşır", () => {
    // Kart bunu gösteriyor: KULLANICININ beyanı, portföyün ölçümü değil.
    expect(toRiskSummary(risk()).surveyScore).toBe(2);
  });

  it("anket doldurulmamışsa puan UYDURULMAZ", () => {
    // Profilden geriye puan üretmek (Korumacı -> 1 veya 2?) verilmemiş bir
    // cevabı verilmiş göstermek olurdu (AK 5.5). Kartta gösterge çizilmez.
    expect(toRiskSummary(risk({ risk_survey_score: null })).surveyScore).toBeNull();
  });

  it("profil adını Türkçeleştirir", () => {
    expect(toRiskSummary(risk()).profileLabel).toBe("Korumacı");
    expect(toRiskSummary(risk({ risk_profile: "aggressive" })).profileLabel).toBe("Agresif");
  });
});

describe("performansçının varlık sınıfı", () => {
  it("SEMBOL üzerinden varlık tablosundan bulunur", () => {
    // Boş bırakıldığında ekranda sonu ayraçla biten bir metin görünüyordu
    // ("Tüpraş · ").
    const d = toDashboardData({
      summary: OZET,
      performance: performans(),
      range: "3A",
      holdings: {
        user_id: "u1",
        as_of: "2026-08-20",
        holdings: [
          {
            symbol: "TUPRS",
            name: "Tüpraş",
            asset_class: "stock",
            currency: "TRY",
            quantity: 10,
            current_price_try: 391.75,
            market_value_try: 3917.5,
            weight_percent: 1,
            avg_cost_try: 172.63,
            cost_basis_try: 1726.3,
            unrealized_pnl_try: 2191.2,
            unrealized_pnl_percent: 126.91,
            realized_pnl_try: 0,
            price_missing: false,
          },
        ],
        best_performer: { symbol: "TUPRS", name: "Tüpraş", unrealized_pnl_percent: 126.91 },
        worst_performer: null,
        excluded_symbols: [],
      },
      transactions: null,
      risk: null,
      darkTheme: false,
    });

    expect(d.bestPerformer?.assetClass).toBe("Hisse Senedi");
  });
});
