import { apiGet, apiPost } from "./client";

/**
 * Al/Sat uçlarının HAM şekli — `backend/app/schemas/trade.py` ile birebir.
 *
 * FİYAT GÖNDERİLMEZ. İstek gövdesinde fiyat alanı yok ve olmamalı: istemciye
 * fiyat yazdırmak, tarayıcı üzerinden istenen fiyattan alım yapmaya kapı
 * bırakırdı. Sunucu fiyatı kendi çözüyor ve `preview` ile `execute` aynı
 * değeri kullanıyor.
 */

export type ApiTradeSide = "buy" | "sell";

export interface ApiTradableAsset {
  symbol: string;
  name: string;
  asset_class: "stock" | "bond" | "currency" | "precious_metal" | "cash";
  currency: string;
  risk_level: number;
  /** Listedeki fiyat KAYITLI kapanış; canlı fiyat ön izlemede çekilir. */
  price: number | null;
  price_date: string | null;
  price_source: string | null;
  price_stale: boolean;
  can_buy: boolean;
  /** Alınamıyorsa sebebi — kilidin nedeni gösterilmezse kullanıcı hatayı
   *  kendinde arar. */
  block_reason: string | null;
  held_quantity: number;
  /** Miktar kaç ondalıkla girilebilir (hisse 1, maden 0,01). */
  quantity_step: number;
}

export interface ApiTradableList {
  user_id: string;
  survey_score: number | null;
  cash_balance: number;
  assets: ApiTradableAsset[];
}

export interface ApiTradePreview {
  symbol: string;
  name: string;
  side: ApiTradeSide;
  /** Sınıf hassasiyetine YUVARLANMIŞ miktar; girilenden farklı olabilir. */
  quantity: number;
  price: number;
  price_date: string;
  price_stale: boolean;
  /** Fiyat sağlayıcıdan o an mı çekildi, yoksa kayıtlı kapanış mı? */
  price_is_live: boolean;
  currency: string;
  fx_rate_to_try: number;
  gross_try: number;
  fee_try: number;
  cash_delta_try: number;
  cash_before: number;
  cash_after: number;
  held_before: number;
  held_after: number;
}

export interface ApiTradeResult {
  transaction_id: string;
  executed_at: string;
  preview: ApiTradePreview;
}

export function fetchTradableAssets(userId: string) {
  return apiGet<ApiTradableList>(`/api/trade/${userId}/assets`);
}

export function previewTrade(
  userId: string,
  symbol: string,
  side: ApiTradeSide,
  quantity: number,
) {
  return apiPost<ApiTradePreview>(`/api/trade/${userId}/preview`, { symbol, side, quantity });
}

export function executeTrade(
  userId: string,
  symbol: string,
  side: ApiTradeSide,
  quantity: number,
) {
  return apiPost<ApiTradeResult>(`/api/trade/${userId}/execute`, { symbol, side, quantity });
}

export function depositCash(userId: string, amount: number) {
  return apiPost<{ cash_balance: number }>(`/api/trade/${userId}/deposit`, { amount });
}
