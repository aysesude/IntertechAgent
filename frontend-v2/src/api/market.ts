import { apiGet } from "./client";
import type { ApiAssetClass } from "./portfolio";

/**
 * Piyasa ekranının HAM uç şekilleri.
 *
 * `backend/app/schemas/market.py` ile birebir eşleşir. Hesaplanamayan
 * değerler `null` gelir, `0` değil: "değişmedi" ile "hesaplanamadı" farklı
 * şeyler ve ikincisi kullanıcıya "—" olarak gösterilmeli (AK 5.5).
 */

export interface ApiMarketIndicator {
  symbol: string;
  name: string;
  asset_class: ApiAssetClass;
  price: number;
  /** Bir önceki işlem gününe göre değişim. Seride tek nokta varsa `null`. */
  change_percent: number | null;
  /** Fiyatın ait olduğu gün (ISO). Bugün olmak ZORUNDA DEĞİL. */
  price_date: string;
  source: string;
  stale: boolean;
}

export interface ApiMarketIndicatorList {
  as_of: string;
  indicators: ApiMarketIndicator[];
  missing_symbols: string[];
}

/**
 * Tek bir başlık. `url` YOK ve olmayacak: BloombergHT son dakika
 * maddelerinin ayrı adresi bulunmuyor (ölçüldü), kaynak listenin tamamına
 * giden tek adrestir.
 */
export interface ApiMarketHeadline {
  title: string;
  published_at: string | null;
}

export interface ApiMarketHeadlineList {
  headlines: ApiMarketHeadline[];
  source_name: string;
  source_url: string;
}

export interface ApiPortfolioInfluenceRow {
  symbol: string;
  name: string;
  asset_class: ApiAssetClass;
  weight_percent: number | null;
  change_percent: number | null;
}

export interface ApiPortfolioInfluenceList {
  as_of: string;
  rows: ApiPortfolioInfluenceRow[];
}

export function fetchMarketIndicators(): Promise<ApiMarketIndicatorList> {
  return apiGet<ApiMarketIndicatorList>("/api/market/indicators");
}

/**
 * Canlı gündem. Kaynağa ulaşılamazsa uç 503 döner ve bu fonksiyon HATA
 * FIRLATIR — boş liste dönmek "bugün haber yok" gibi okunurdu.
 */
export function fetchMarketHeadlines(): Promise<ApiMarketHeadlineList> {
  return apiGet<ApiMarketHeadlineList>("/api/market/headlines");
}

export function fetchPortfolioInfluence(userId: string): Promise<ApiPortfolioInfluenceList> {
  return apiGet<ApiPortfolioInfluenceList>(`/api/market/influence/${userId}`);
}

/**
 * Yaklaşan KAP bildirimi. Tek tarih değil PENCERE taşır: `due_date` aralığın
 * sonu ve kullanıcı için bağlayıcı olan gün.
 */
export interface ApiMarketCalendarEntry {
  symbol: string;
  company: string;
  subject: string;
  period: string | null;
  start_date: string | null;
  due_date: string;
}

export interface ApiMarketCalendarList {
  entries: ApiMarketCalendarEntry[];
  source_name: string;
  source_url: string;
}

/** Boş liste hata DEĞİL: hisse yoksa ya da yakında bildirim yoksa boş döner. */
export function fetchMarketCalendar(userId: string): Promise<ApiMarketCalendarList> {
  return apiGet<ApiMarketCalendarList>(`/api/market/calendar/${userId}`);
}
