import type { ApiBenchmarkComparison } from "@/api/portfolio";
import { BRAND, DANGER } from "@/utils/colors";

/**
 * Kıyaslama yanıtını "Varlıklar Arası Karşılaştırmalı Getiri" kartının
 * çubuklarına çevirir.
 *
 * Kart BEŞ çubuk gösteriyor: portföyün kendisi + dört kıyas enstrümanı
 * (BIST100, USD, EUR, Altın). Backend `BENCHMARK_SYMBOLS` sırasını koruyarak
 * döndürüyor; burada sıra DEĞİŞTİRİLMİYOR, yalnızca portföy başa ekleniyor —
 * dönem değişince çubukların yer değiştirmesi karşılaştırmayı okunmaz yapar.
 */

export interface BenchmarkBar {
  id: string;
  label: string;
  color: string;
  /** Dönem başı ile bugün arası toplam % getiri. Hesaplanamadıysa `null`. */
  returnPct: number | null;
}

/**
 * Sembol → kartta görünecek KISA etiket.
 *
 * Backend'in `name` alanı tam unvanı taşıyor ("Amerikan Doları", "Gram
 * Altın"); çubuk altında yan yana beş uzun etiket sığmıyor. Tanınmayan bir
 * sembol gelirse `name`'e düşülüyor — sessizce çubuğu düşürmek, kullanıcının
 * eksik bir kıyas gördüğünü fark etmemesi demek olurdu.
 */
const KISA_ETIKET: Record<string, string> = {
  XU100: "BIST100",
  USDTRY: "USD",
  EURTRY: "EUR",
  XAUTRY: "Altın",
};

export function toBenchmarkBars(kiyas: ApiBenchmarkComparison): BenchmarkBar[] {
  return [
    {
      id: "portfoy",
      label: "Portföyüm",
      // Tek vurgulu çubuk: kıyas enstrümanları aynı tonda kalınca göz
      // doğrudan "benim getirim nerede" sorusuna gidiyor.
      color: DANGER,
      returnPct: kiyas.portfolio_return_percent,
    },
    ...kiyas.benchmarks.map((b) => ({
      id: b.symbol,
      label: KISA_ETIKET[b.symbol] ?? b.name,
      color: BRAND,
      returnPct: b.return_percent,
    })),
  ];
}

/**
 * Kullanıcıya gösterilecek uyarı metni; uyarı yoksa `null`.
 *
 * İki durum sessiz kalmamalı:
 *
 * - **Kırpılmış pencere:** portföy pencereden gençse başlangıç ilk varlık
 *   alımına çekiliyor. "Yıllık" yazıp dört aylık getiri göstermek, kıyası
 *   olduğundan iyi ya da kötü gösterir.
 * - **Dışarıda kalan varlık:** pencere başında fiyatı olmayan varlık hesaba
 *   katılmıyor; portföy getirisi o varlığı içermiyor demektir.
 */
export function benchmarkUyarisi(kiyas: ApiBenchmarkComparison): string | null {
  const parcalar: string[] = [];
  if (kiyas.truncated_to_inception) {
    parcalar.push(`portföy bu dönemden genç, başlangıç ${kiyas.start_date} olarak alındı`);
  }
  if (kiyas.excluded_symbols.length > 0) {
    parcalar.push(
      `dönem başında fiyatı olmayan ${kiyas.excluded_symbols.join(", ")} hesaba katılmadı`,
    );
  }
  return parcalar.length > 0 ? parcalar.join(" · ") : null;
}
