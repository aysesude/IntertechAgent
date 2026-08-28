import type { ApiRiskAssessment } from "@/api/risk";
import type {
  ApiHoldingsValuation,
  ApiPerformanceResult,
  ApiPortfolioSummary,
  ApiTransactionList,
  ApiTransactionRow,
  ApiWindow,
} from "@/api/portfolio";
import { DARK_ASSET_CLASS_COLORS } from "@/data/assetColors";
import { formatDateDMY, formatSignedTRY, formatTRY } from "@/utils/format";
import {
  ASSET_CLASS_IDS,
  ASSET_CLASS_LABELS,
  LIGHT_ASSET_CLASS_COLORS,
  RISK_LEVEL_LABELS,
  RISK_LEVEL_ORDINALS,
  RISK_PROFILE_LABELS,
} from "@/adapters/shared";
import type {
  AssetAllocationSlice,
  DashboardData,
  PerformanceRange,
  PortfolioSummary,
  RangeKey,
  RiskSummary,
  Transaction,
} from "@/types/finance";

/**
 * Backend'in ham çıktısını Dashboard'un görünüm modeline çevirir.
 *
 * SAF FONKSİYONLAR: ağ, React, tarih "şu an"ı yok. Böylece bileşenlere hiç
 * dokunmadan birim testlenebiliyor ve alan eşlemesi tek yerde toplanıyor.
 *
 * DOLDURULMAYAN ALANLAR: `riskScore`, `realReturnPct`, `recommendations` gibi
 * kaynağı olmayan alanlar BİLEREK atlanıyor. Uydurma bir değerle doldurmak
 * (ör. 0 ya da tahmini bir skor) ekranda gerçek sanılırdı — CLAUDE.md §4.
 */

// ---------------------------------------------------------------------------
// Varlık sınıfı eşlemesi
// ---------------------------------------------------------------------------

/** Grafik dönemi ↔ backend penceresi. */
export const WINDOW_BY_RANGE: Record<RangeKey, ApiWindow> = {
  "1A": "1m",
  "3A": "3m",
  "6A": "6m",
  "1Y": "12m",
};

const RANGE_SUBTITLES: Record<RangeKey, string> = {
  "1A": "Son 1 ay",
  "3A": "Son 3 ay",
  "6A": "Son 6 ay",
  "1Y": "Son 1 yıl",
};

// ---------------------------------------------------------------------------
// Özet
// ---------------------------------------------------------------------------

export function toSummary(
  ozet: ApiPortfolioSummary,
  performans?: ApiPerformanceResult,
): PortfolioSummary {
  const gunlukYuzde = performans?.summary.changes.daily ?? null;

  return {
    totalValue: ozet.total_value,
    costBasis: ozet.total_cost_basis,
    // Kâr/zararın tabanı: hesapta duran para da kullanıcının koyduğu paradır,
    // kazanç değildir (bkz. docs/API.md).
    netInvested: ozet.net_invested,
    totalPL: ozet.total_gain_loss.amount,
    totalPLPct: ozet.total_gain_loss.percent,
    // Backend günlük değişimi YÜZDE olarak veriyor; TL karşılığı bugünkü
    // değerden geriye çözülüyor. Yeterli geçmiş yoksa `null` gelir ve
    // alanların ikisi de doldurulmaz.
    ...(gunlukYuzde === null
      ? {}
      : {
          todayChangePct: gunlukYuzde,
          todayChange: ozet.total_value - ozet.total_value / (1 + gunlukYuzde / 100),
        }),
    ...(performans?.summary.change_percent == null
      ? {}
      : { periodReturnPct: performans.summary.change_percent }),
  };
}

// ---------------------------------------------------------------------------
// Performans serisi
// ---------------------------------------------------------------------------

/**
 * Eksen etiketi. Uzun pencerelerde her noktaya tam tarih yazmak ekseni
 * okunmaz hale getiriyor; 12 ayda ay adı, kısa pencerelerde gün+ay.
 */
function noktaEtiketi(isoTarih: string, aylik: boolean): string {
  const [yil, ay, gun] = isoTarih.split("-").map(Number);
  const AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
  const ayAdi = AYLAR[(ay - 1 + 12) % 12];
  if (aylik) return `${ayAdi} ${String(yil).slice(2)}`;
  return `${gun} ${ayAdi}`;
}

export function toPerformanceRange(
  sonuc: ApiPerformanceResult,
  key: RangeKey,
): PerformanceRange {
  const aylik = key === "1Y";
  return {
    key,
    subtitle: RANGE_SUBTITLES[key],
    truncatedToInception: sonuc.truncated_to_inception,
    returnPct: sonuc.summary.change_percent,
    // Tasarımdaki "Mayıs düzeltmesi" gibi elle konmuş işaretçilerin veri
    // karşılığı yok; üretmiyoruz.
    annotationIndex: null,
    points: sonuc.series.map((nokta) => ({
      label: noktaEtiketi(nokta.date, aylik),
      portfolio: nokta.value_try,
      invested: nokta.invested_try,
    })),
  };
}

// ---------------------------------------------------------------------------
// Varlık dağılımı
// ---------------------------------------------------------------------------

export function toAllocation(
  ozet: ApiPortfolioSummary,
  varliklar: ApiHoldingsValuation | null,
  koyuTema: boolean,
): AssetAllocationSlice[] {
  const palet = koyuTema ? DARK_ASSET_CLASS_COLORS : LIGHT_ASSET_CLASS_COLORS;

  return ozet.allocation.map((dilim) => {
    const id = ASSET_CLASS_IDS[dilim.asset_class];
    // Alt kırılım varlık tablosundan geliyor: o sınıftaki tek tek enstrümanlar.
    // Fiyatı bulunamayanlar (`price_missing`) dışarıda bırakılıyor — değeri
    // `null` olan satırı yüzdeye çevirmek yanlış sayı üretirdi.
    const altlar = (varliklar?.holdings ?? [])
      .filter((h) => h.asset_class === dilim.asset_class && !h.price_missing)
      .sort((a, b) => (b.market_value_try ?? 0) - (a.market_value_try ?? 0));

    return {
      id,
      name: ASSET_CLASS_LABELS[dilim.asset_class],
      value: dilim.value,
      formattedValue: formatTRY(dilim.value),
      pct: dilim.percent,
      color: palet[id].color,
      highlightColor: palet[id].highlight,
      subcategories: altlar.map((h) => {
        const deger = h.market_value_try ?? 0;
        return {
          name: h.name,
          value: deger,
          formattedValue: formatTRY(deger),
          // Sınıf İÇİNDEKİ pay — dilimin kendi toplamına göre.
          pct: dilim.value > 0 ? Math.round((deger / dilim.value) * 1000) / 10 : 0,
        };
      }),
    };
  });
}

// ---------------------------------------------------------------------------
// İşlemler
// ---------------------------------------------------------------------------

const TRANSACTION_LABELS: Record<ApiTransactionRow["type"], string> = {
  buy: "Alım",
  sell: "Satım",
  deposit: "Para Yatırma",
  withdraw: "Para Çekme",
  dividend: "Temettü",
  interest: "Faiz",
  fee: "Komisyon",
};

/**
 * Son işlemler listesi, YENİDEN ESKİYE sıralı ve `limit` kadar.
 *
 * Backend eskiden yeniye döndürüyor (defter sırası); ekranda en son olan
 * üstte olmalı.
 */
export function toTransactions(liste: ApiTransactionList, limit = 6): Transaction[] {
  return [...liste.transactions]
    .reverse()
    .slice(0, limit)
    .map((islem, sira) => {
      const tutar = islem.cash_amount_try;
      const miktarVar = islem.symbol !== null && islem.quantity !== 0;
      return {
        id: `${islem.transaction_date}-${islem.type}-${islem.symbol ?? "nakit"}-${sira}`,
        title: islem.symbol
          ? `${TRANSACTION_LABELS[islem.type]} · ${islem.symbol}`
          : TRANSACTION_LABELS[islem.type],
        date: formatDateDMY(islem.transaction_date),
        detail: miktarVar
          ? `${islem.quantity} adet${islem.price !== null ? ` · ${formatTRY(islem.price)}` : ""}`
          : "",
        amount: tutar,
        formattedAmount: formatSignedTRY(tutar),
        // İşaret defterden geliyor: o gün hesaptan fiilen çıkan/giren TL.
        direction: tutar > 0 ? "in" : tutar < 0 ? "out" : "neutral",
      };
    });
}


// ---------------------------------------------------------------------------
// Risk
// ---------------------------------------------------------------------------

export function toRiskSummary(risk: ApiRiskAssessment): RiskSummary {
  return {
    levelLabel: risk.risk_level ? RISK_LEVEL_LABELS[risk.risk_level] : null,
    level: risk.risk_level ? RISK_LEVEL_ORDINALS[risk.risk_level] : null,
    surveyScore: risk.risk_survey_score,
    annualizedVolatilityPct: risk.metrics.annualized_volatility_percent,
    withinProfile: risk.is_within_profile,
    profileLabel: RISK_PROFILE_LABELS[risk.risk_profile],
    // Birden fazla uyarı olabilir; kartta yer olmadığı için ilki gösteriliyor,
    // tamamı Risk ekranında listelenecek.
    warning: risk.warnings.length > 0 ? risk.warnings[0] : null,
  };
}

// ---------------------------------------------------------------------------
// Bileşim
// ---------------------------------------------------------------------------

export interface DashboardSources {
  summary: ApiPortfolioSummary;
  performance: ApiPerformanceResult;
  range: RangeKey;
  /** Kısmi başarısızlıkta `null` gelebilir; dağılım alt kırılımsız çizilir. */
  holdings: ApiHoldingsValuation | null;
  transactions: ApiTransactionList | null;
  /** Risk ucu düşerse `null`; kart "hesaplanamadı" gösterir. */
  risk: ApiRiskAssessment | null;
  darkTheme: boolean;
}

/** Sembolden varlık sınıfının Türkçe adını bulur; bulunamazsa boş döner. */
function _sinifAdi(varliklar: ApiHoldingsValuation, symbol: string): string {
  const satir = varliklar.holdings.find((h) => h.symbol === symbol);
  return satir ? ASSET_CLASS_LABELS[satir.asset_class] : "";
}

export function toDashboardData(kaynak: DashboardSources): DashboardData {
  const { summary: ozet, performance: performans, holdings, transactions } = kaynak;

  return {
    summary: toSummary(ozet, performans),
    // Yalnızca SEÇİLİ dönem yükleniyor: dördünü birden çekmek dört ek istek
    // demek ve kullanıcı çoğu zaman tek döneme bakıyor.
    performance: { [kaynak.range]: toPerformanceRange(performans, kaynak.range) } as Record<
      RangeKey,
      PerformanceRange
    >,
    allocation: toAllocation(ozet, holdings, kaynak.darkTheme),
    transactions: transactions ? toTransactions(transactions) : [],
    // Öneriler risk ajanının senaryolarından gelecek (Faz 5). Kaynağı yokken
    // üretmiyoruz.
    recommendations: [],
    // Varlık sınıfı, performansçının SEMBOLÜ üzerinden varlık tablosundan
    // bulunuyor. Boş bırakıldığında ekranda sonu ayraçla biten bir metin
    // görünüyordu ("Tüpraş · ").
    ...(holdings?.best_performer
      ? {
          bestPerformer: {
            name: holdings.best_performer.name,
            assetClass: _sinifAdi(holdings, holdings.best_performer.symbol),
            returnPct: holdings.best_performer.unrealized_pnl_percent,
          },
        }
      : {}),
    ...(holdings?.worst_performer
      ? {
          worstPerformer: {
            name: holdings.worst_performer.name,
            assetClass: _sinifAdi(holdings, holdings.worst_performer.symbol),
            returnPct: holdings.worst_performer.unrealized_pnl_percent,
          },
        }
      : {}),
    ...(kaynak.risk ? { risk: toRiskSummary(kaynak.risk) } : {}),
    instrumentCount: ozet.holdings_count,
    assetClassCount: ozet.allocation.length,
    lastUpdated: formatDateDMY(ozet.as_of),
  };
}

/**
 * Fiyat verisinin tazeliği hakkında gösterilecek uyarı; yoksa `null`.
 *
 * `docs/API.md` bunu ŞART koşuyor: özet her varlığı kendi son fiyatıyla
 * değerliyor, dolayısıyla tek bir tarih tüm portföyü tarif etmiyor. Yalnızca
 * `as_of` gösterilirse özet olduğundan taze görünür.
 */
export function priceFreshnessWarning(ozet: ApiPortfolioSummary): string | null {
  if (!ozet.oldest_price_date || ozet.oldest_price_date === ozet.as_of) return null;
  return `Portföyün bir kısmı daha eski fiyatlarla değerlendi (${formatDateDMY(
    ozet.oldest_price_date,
  )} – ${formatDateDMY(ozet.as_of)}).`;
}