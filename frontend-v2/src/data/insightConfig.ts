// İçgörü motorunun tüm eşikleri tek yerden — kurallar (src/utils/insights.ts)
// bu sabitleri okur, hiçbir eşiği kendi içinde gömmez.

/** TODO: backend'den gelecek. */
export const MONTHLY_INFLATION_PCT = 2.8;

/** TODO: backend'den gelecek. */
export const ANNUAL_INFLATION_PCT = 34;

/** Hedef vs gerçekleşen ağırlık sapması için üst sınır (puan). */
export const WEIGHT_DEVIATION_LIMIT = 5;

/** Nakit ağırlığı bu yüzdeyi aşarsa uyarı üretilir. */
export const CASH_LIMIT_PCT = 8;

/** Tek bir varlığın portföy içindeki payı bu yüzdeyi aşarsa uyarı üretilir. */
export const SINGLE_HOLDING_LIMIT_PCT = 20;

/** Risk skoru için hedef bant. */
export const RISK_BAND = { low: 45, high: 60 };

/** Bu değerin altındaki (veya eşit) getiri "zayıf performans" sayılır. */
export const WEAK_RETURN_PCT = -4;

/** Bu değerin üzerindeki (veya eşit) getiri "güçlü performans" sayılır. */
export const STRONG_RETURN_PCT = 10;

/** Portföy-benchmark farkının anlamlı sayılması için eşik (puan). */
export const BENCHMARK_GAP_PCT = 1.5;

/** Döviz ağırlığı bu yüzdeyi aşarsa bilgilendirme üretilir. */
export const FX_LIMIT_PCT = 25;

/** Döndürülecek maksimum içgörü sayısı. */
export const MAX_INSIGHTS = 3;
