import { apiGet } from "./client";

/**
 * Portföy uçlarının HAM şekilleri.
 *
 * Backend sözleşmesiyle birebir aynı (`backend/app/schemas/portfolio.py`):
 * `snake_case`, `Decimal` alanlar JSON'a `number` olarak serialize ediliyor.
 * Ekranların beklediği görünüm modeline dönüşüm `src/adapters/` altında
 * yapılır — bu dosya yalnızca "sunucu ne diyor"u tarif eder.
 *
 * Hesaplanamayan değerler `null` gelir, `0` değil: eksik veriyi sıfırla
 * doldurmak sessizce yanlış sayı üretmek olurdu (AK 5.5).
 */

export type ApiAssetClass = "stock" | "precious_metal" | "currency" | "bond" | "cash";
export type ApiWindow = "1m" | "3m" | "6m" | "12m";

export interface ApiAllocationItem {
  asset_class: ApiAssetClass;
  value: number;
  percent: number;
}

export interface ApiPortfolioSummary {
  user_id: string;
  /** Kullanılan fiyatların EN YENİ günü. */
  as_of: string;
  /**
   * Kullanılan fiyatların EN ESKİ günü. `as_of`'tan farklıysa portföyün bir
   * kısmı daha eski fiyatla değerlenmiş demektir ve arayüz bunu BELİRTMELİ —
   * yalnızca `as_of` gösterilirse özet olduğundan taze görünür.
   */
  oldest_price_date: string | null;
  total_value: number;
  total_cost_basis: number;
  net_invested: number;
  total_gain_loss: { amount: number; percent: number };
  allocation: ApiAllocationItem[];
  holdings_count: number;
}

export interface ApiHoldingRow {
  symbol: string;
  name: string;
  asset_class: ApiAssetClass;
  currency: string;
  quantity: number;
  current_price_try: number | null;
  market_value_try: number | null;
  weight_percent: number | null;
  avg_cost_try: number;
  cost_basis_try: number;
  unrealized_pnl_try: number | null;
  unrealized_pnl_percent: number | null;
  realized_pnl_try: number;
  /** Fiyatı bulunamayan varlık listeden DÜŞMEZ; bu bayrakla döner. */
  price_missing: boolean;
}

export interface ApiPerformerRef {
  symbol: string;
  name: string;
  unrealized_pnl_percent: number;
}

export interface ApiHoldingsValuation {
  user_id: string;
  as_of: string;
  holdings: ApiHoldingRow[];
  /** Kodda seçilir; dil modelinin karşılaştırma yapması yasak. */
  best_performer: ApiPerformerRef | null;
  worst_performer: ApiPerformerRef | null;
  excluded_symbols: string[];
}

export interface ApiPerformancePoint {
  date: string;
  value_try: number;
  /** Kümülatif dış akış (yatırılan − çekilen). */
  invested_try: number;
}

export interface ApiPerformanceResult {
  user_id: string;
  as_of: string;
  window: ApiWindow;
  granularity: string;
  inception: string;
  truncated_to_inception: boolean;
  series: ApiPerformancePoint[];
  summary: {
    start_value: number;
    end_value: number;
    change_amount: number;
    /** TWR — dış para akışından arındırılmış. Yeterli veri yoksa `null`. */
    change_percent: number | null;
    realized_pnl: number;
    unrealized_pnl: number;
    changes: {
      daily: number | null;
      weekly: number | null;
      monthly: number | null;
    };
  };
}

export type ApiTransactionType =
  | "buy"
  | "sell"
  | "deposit"
  | "withdraw"
  | "dividend"
  | "interest"
  | "fee";

export interface ApiTransactionRow {
  transaction_date: string;
  type: ApiTransactionType;
  symbol: string | null;
  quantity: number;
  price: number | null;
  currency: string;
  fx_rate_to_try: number;
  fee_try: number;
  /** İşaretli ve işlem anındaki kurla dondurulmuş: o gün hesaptan çıkan/giren TL. */
  cash_amount_try: number;
  position_after: number | null;
}

export interface ApiTransactionList {
  user_id: string;
  start_date: string | null;
  end_date: string | null;
  transactions: ApiTransactionRow[];
}

export function fetchPortfolioSummary(userId: string) {
  return apiGet<ApiPortfolioSummary>(`/api/portfolio/${userId}`);
}

export function fetchHoldings(userId: string) {
  return apiGet<ApiHoldingsValuation>(`/api/portfolio/${userId}/holdings`);
}

export function fetchPerformance(userId: string, window: ApiWindow) {
  return apiGet<ApiPerformanceResult>(`/api/portfolio/${userId}/performance?window=${window}`);
}

export function fetchTransactions(userId: string) {
  return apiGet<ApiTransactionList>(`/api/portfolio/${userId}/transactions`);
}
