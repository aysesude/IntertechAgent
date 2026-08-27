import type {
  ApiMarketCalendarList,
  ApiMarketHeadlineList,
  ApiMarketIndicatorList,
  ApiPortfolioInfluenceList,
} from "@/api/market";
import type { CalendarEvent, InfluenceRow, MarketIndicator, NewsItem } from "@/types/finance";
import { formatDateDMY, formatNumberTR, formatTRY2 } from "@/utils/format";

/**
 * Piyasa ekranının ham uç verisini görünüm modeline çevirir.
 *
 * SAF fonksiyonlar: ağ, tarayıcı ya da React yok — böylece ölçüm yapılabilir
 * biçimde test edilebiliyorlar (bkz. market.test.ts).
 *
 * DOLDURULMAYAN ALANLAR: `NewsItem.tag`, `aiSummary`, `impact`, `sourceCount`
 * hep `null` döner. Bunların canlı kaynakta karşılığı yok (BloombergHT son
 * dakika akışı yalnızca başlık ve zaman veriyor) ve model çalıştırıp
 * doldurmak, başlık dışında veri olmadığı için detay uydurmak demekti.
 * Arayüz bu alanları "—" gösterir ya da hiç çizmez.
 */

/** Şeritte kısa etiket kullanılıyor; uzun ad ("Amerikan Doları") sığmıyor. */
const GOSTERGE_ETIKETLERI: Record<string, string> = {
  XU100: "BIST 100",
  USDTRY: "USD/TRY",
  EURTRY: "EUR/TRY",
  XAUTRY: "Gram Altın",
};

/**
 * Endeks puanı para değil: "14.514,82" doğru, "₺14.514,82" yanlış.
 * Sembole göre ayrılıyor çünkü `asset_class` bu ayrımı yapmıyor — XU100
 * evrende hisse sınıfında duruyor (fiyatlanabilmesi için).
 */
const PARA_BIRIMSIZ_SEMBOLLER = new Set(["XU100"]);

function fiyatBicimle(symbol: string, price: number): string {
  return PARA_BIRIMSIZ_SEMBOLLER.has(symbol) ? formatNumberTR(price, 2) : formatTRY2(price);
}

export function toMarketIndicators(veri: ApiMarketIndicatorList): MarketIndicator[] {
  return veri.indicators.map((ind) => ({
    id: ind.symbol,
    label: GOSTERGE_ETIKETLERI[ind.symbol] ?? ind.name,
    value: fiyatBicimle(ind.symbol, ind.price),
    changePct: ind.change_percent,
    priceDate: formatDateDMY(ind.price_date),
    stale: ind.stale,
  }));
}

/**
 * "3 dk önce", "2 sa önce", "24.08.2026".
 *
 * Bir günden eskiyse göreli ifade bırakılıp tam tarih yazılır: "38 sa önce"
 * okunabilir değil ve haberin hangi güne ait olduğu finansal bağlamda önemli.
 * Tarih yoksa "—" döner; uydurma bir zaman yazılmaz.
 */
export function gorecelizaman(isoTarih: string | null, simdi: Date = new Date()): string {
  if (!isoTarih) return "—";
  const t = new Date(isoTarih);
  if (Number.isNaN(t.getTime())) return "—";

  const dakika = Math.floor((simdi.getTime() - t.getTime()) / 60000);
  // Gelecek tarih: sunucu ile tarayıcı saati birkaç saniye kayabilir,
  // "-1 dk önce" yazmaktansa "az önce" demek doğru.
  if (dakika < 1) return "az önce";
  if (dakika < 60) return `${dakika} dk önce`;
  const saat = Math.floor(dakika / 60);
  if (saat < 24) return `${saat} sa önce`;
  return formatDateDMY(isoTarih);
}

export function toNewsItems(veri: ApiMarketHeadlineList, simdi: Date = new Date()): NewsItem[] {
  return veri.headlines.map((h, i) => ({
    // Başlık metni kimlik olarak kullanılmıyor: aynı başlık iki kez
    // geçebilir (düzeltilmiş bültenler) ve React anahtarı çakışırdı.
    id: `${veri.source_name}-${i}`,
    tag: null,
    isPortfolioRelevant: false,
    source: veri.source_name,
    time: gorecelizaman(h.published_at, simdi),
    title: h.title,
    aiSummary: null,
    impact: null,
    sourceCount: null,
  }));
}

export function toInfluenceRows(veri: ApiPortfolioInfluenceList): InfluenceRow[] {
  return veri.rows.map((r) => ({
    id: r.symbol,
    name: r.symbol,
    changePct: r.change_percent,
    weightPct: r.weight_percent,
  }));
}

const AY_KISALTMALARI = [
  "Oca", "Şub", "Mar", "Nis", "May", "Haz",
  "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara",
];

/** `"2026-11-09"` -> `"09 Kas"`. Kart dar; tam tarih sığmıyor. */
function kisaTarih(iso: string): string {
  const [yil, ay, gun] = iso.split("-").map(Number);
  const kisaltma = AY_KISALTMALARI[(ay ?? 1) - 1];
  if (!kisaltma || !gun || !yil) return iso;
  return `${String(gun).padStart(2, "0")} ${kisaltma}`;
}

/**
 * Takvim kartı satırları.
 *
 * Gösterilen tarih `due_date`, yani dosyalama penceresinin SONU — KAP tek bir
 * tarih değil bir aralık yayımlıyor ve kullanıcı için bağlayıcı olan gün
 * aralığın sonudur. Başlangıcı göstermek kartı gereksiz kalabalıklaştırır.
 */
export function toCalendarEvents(veri: ApiMarketCalendarList): CalendarEvent[] {
  return veri.entries.map((e, i) => ({
    // Aynı şirket aynı gün iki bildirim bekliyor olabilir; sıra numarası
    // anahtarın benzersizliğini garanti eder.
    id: `${e.symbol}-${e.due_date}-${i}`,
    date: kisaTarih(e.due_date),
    description: e.period ? `${e.symbol} · ${e.subject} (${e.period})` : `${e.symbol} · ${e.subject}`,
  }));
}
