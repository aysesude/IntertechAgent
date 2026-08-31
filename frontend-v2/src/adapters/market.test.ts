import { describe, expect, it } from "vitest";
import type {
  ApiMarketCalendarList,
  ApiMarketHeadlineList,
  ApiMarketIndicatorList,
  ApiPortfolioInfluenceList,
} from "@/api/market";
import {
  gorecelizaman,
  toCalendarEvents,
  toInfluenceRows,
  toMarketIndicators,
  toNewsItems,
} from "./market";

/**
 * Piyasa adapter testleri.
 *
 * Odak `null` davranışı: bu ekranın kaynaklarında hesaplanamayan değer
 * NORMAL (fiyat geçmişi tek günse değişim yok, canlı akışta özet yok) ve
 * bunların 0 ya da boş metne dönüşmesi kullanıcıya yanlış bilgi verir.
 */

const GOSTERGELER: ApiMarketIndicatorList = {
  as_of: "2026-08-24",
  indicators: [
    {
      symbol: "XU100",
      name: "BIST 100 Endeksi",
      asset_class: "stock",
      price: 14514.82,
      change_percent: 0.82,
      price_date: "2026-08-22",
      source: "yfinance",
      stale: false,
      currency: null,
    },
    {
      symbol: "USDTRY",
      name: "Amerikan Doları",
      asset_class: "currency",
      price: 41.86,
      change_percent: null,
      price_date: "2026-08-22",
      source: "tcmb",
      stale: true,
      currency: "TRY",
    },
  ],
  missing_symbols: [],
};

describe("toMarketIndicators", () => {
  it("endeksi para birimsiz, kuru TL olarak biçimler", () => {
    const [endeks, kur] = toMarketIndicators(GOSTERGELER);

    expect(endeks.label).toBe("BIST 100");
    expect(endeks.value).not.toContain("₺");
    expect(kur.value).toContain("₺");
  });

  it("TRY DIŞI göstergeyi kendi birimiyle biçimler", () => {
    // Brent doları ₺ ile basmak, aynı hatanın Al/Sat ekranındaki hâliydi.
    const [brent] = toMarketIndicators({
      ...GOSTERGELER,
      indicators: [
        {
          symbol: "BRENT",
          name: "Brent Petrol",
          asset_class: "stock",
          price: 88.04,
          change_percent: -1.05,
          price_date: "2026-08-28",
          source: "yfinance",
          stale: false,
          currency: "USD",
        },
      ],
    });

    expect(brent.label).toBe("Brent");
    expect(brent.value).toBe("$88,04");
  });

  it("hesaplanamayan değişimi null olarak TAŞIR, sıfıra çevirmez", () => {
    const [, kur] = toMarketIndicators(GOSTERGELER);

    expect(kur.changePct).toBeNull();
  });

  it("fiyat tarihini ve eskilik bayrağını taşır", () => {
    const [endeks, kur] = toMarketIndicators(GOSTERGELER);

    // Biçim uygulama genelinde `formatDateDMY` ile aynı: gg/aa/yyyy.
    expect(endeks.priceDate).toBe("22/08/2026");
    expect(endeks.stale).toBe(false);
    expect(kur.stale).toBe(true);
  });
});

describe("gorecelizaman", () => {
  const simdi = new Date("2026-08-24T15:00:00+03:00");

  it("bir saatten yeniyi dakika, bir günden yeniyi saat olarak yazar", () => {
    expect(gorecelizaman("2026-08-24T14:38:00+03:00", simdi)).toBe("22 dk önce");
    expect(gorecelizaman("2026-08-24T11:03:00+03:00", simdi)).toBe("3 sa önce");
  });

  it("bir günden eskide tam tarih yazar", () => {
    // "38 sa önce" okunabilir değil ve haberin günü finansal bağlamda önemli.
    expect(gorecelizaman("2026-08-21T18:10:00+03:00", simdi)).toBe("21/08/2026");
  });

  it("tarih yoksa ya da bozuksa uydurmaz", () => {
    expect(gorecelizaman(null, simdi)).toBe("—");
    expect(gorecelizaman("bozuk-tarih", simdi)).toBe("—");
  });

  it("sunucu saati ileriyse negatif süre yazmaz", () => {
    expect(gorecelizaman("2026-08-24T15:00:30+03:00", simdi)).toBe("az önce");
  });
});

describe("toNewsItems", () => {
  const GUNDEM: ApiMarketHeadlineList = {
    headlines: [
      { title: "TCMB: REEL SEKTÖRÜN NET DÖVİZ POZİSYONU...", published_at: "2026-08-24T14:38:00+03:00" },
      { title: "TCMB: REEL SEKTÖRÜN NET DÖVİZ POZİSYONU...", published_at: null },
    ],
    source_name: "BloombergHT",
    source_url: "https://www.bloomberght.com/sondakika",
  };

  it("kaynağı olmayan alanları null bırakır", () => {
    const [ilk] = toNewsItems(GUNDEM, new Date("2026-08-24T15:00:00+03:00"));

    expect(ilk.aiSummary).toBeNull();
    expect(ilk.impact).toBeNull();
    expect(ilk.sourceCount).toBeNull();
    expect(ilk.tag).toBeNull();
    expect(ilk.source).toBe("BloombergHT");
  });

  it("aynı başlık iki kez gelse de kimlikler çakışmaz", () => {
    const [a, b] = toNewsItems(GUNDEM);

    expect(a.id).not.toBe(b.id);
  });
});

describe("toInfluenceRows", () => {
  const ETKI: ApiPortfolioInfluenceList = {
    as_of: "2026-08-24",
    rows: [
      { symbol: "ASELS", name: "Aselsan", asset_class: "stock", weight_percent: 16.4, change_percent: 0.25 },
      { symbol: "TI2", name: "Fon", asset_class: "bond", weight_percent: null, change_percent: null },
    ],
  };

  it("eksik ağırlık ve değişimi null olarak taşır", () => {
    const [asels, fon] = toInfluenceRows(ETKI);

    expect(asels.weightPct).toBe(16.4);
    expect(fon.weightPct).toBeNull();
    expect(fon.changePct).toBeNull();
  });
});

describe("toCalendarEvents", () => {
  const TAKVIM: ApiMarketCalendarList = {
    entries: [
      {
        symbol: "ASELS",
        company: "ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.",
        subject: "Finansal Rapor",
        period: "9 Aylık",
        start_date: "2026-10-01",
        due_date: "2026-11-09",
      },
      {
        symbol: "THYAO",
        company: "TÜRK HAVA YOLLARI A.O.",
        subject: "Finansal Rapor",
        period: null,
        start_date: null,
        due_date: "2026-11-09",
      },
    ],
    source_name: "KAP",
    source_url: "https://www.kap.org.tr/tr",
  };

  it("pencerenin SON gününü kısa biçimde gösterir", () => {
    // Başlangıç (01.10) değil bitiş (09.11): kullanıcı için bağlayıcı olan
    // gün pencerenin sonu.
    expect(toCalendarEvents(TAKVIM)[0].date).toBe("09 Kas");
  });

  it("dönem varsa açıklamaya ekler, yoksa eklemez", () => {
    const [asels, thyao] = toCalendarEvents(TAKVIM);

    expect(asels.description).toBe("ASELS · Finansal Rapor (9 Aylık)");
    expect(thyao.description).toBe("THYAO · Finansal Rapor");
  });

  it("aynı gün iki kayıtta kimlikler çakışmaz", () => {
    const [a, b] = toCalendarEvents(TAKVIM);

    expect(a.id).not.toBe(b.id);
  });
});
