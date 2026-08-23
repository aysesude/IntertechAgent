import type { HoldingLot } from "@/types/finance";

/** Bir partinin güncel toplam değeri. */
export function lotValue(lot: HoldingLot, currentUnitPrice: number): number {
  return lot.quantity * currentUnitPrice;
}

/** Bir partinin olası kâr/zararı (TL). */
export function lotPnl(lot: HoldingLot, currentUnitPrice: number): number {
  return (currentUnitPrice - lot.unitCost) * lot.quantity;
}

/** Bir partinin olası getiri yüzdesi — maliyete göre. */
export function lotReturnPct(lot: HoldingLot, currentUnitPrice: number): number {
  const cost = lot.unitCost * lot.quantity;
  if (cost === 0) return 0;
  return (lotPnl(lot, currentUnitPrice) / cost) * 100;
}

/**
 * Alım tarihinden bugüne kadar geçen gün sayısı. `now` her zaman
 * hesaplanır (varsayılan gerçek `new Date()`) — sabit bir değer olarak
 * saklanmaz, aksi halde zaman geçtikçe yanlış hale gelir.
 */
export function lotDaysHeld(lot: HoldingLot, now: Date = new Date()): number {
  const purchase = new Date(lot.purchaseDate);
  const MS_PER_DAY = 86_400_000;
  // Saat diliminden/gün içi saatten bağımsız kalmak için UTC gün
  // başlangıçları arasındaki farkı alıyoruz.
  const start = Date.UTC(purchase.getFullYear(), purchase.getMonth(), purchase.getDate());
  const end = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((end - start) / MS_PER_DAY);
}

export interface HoldingTotals {
  totalQuantity: number;
  totalValue: number;
  totalCost: number;
  totalPnl: number;
  /** Maliyete göre ağırlıklı getiri yüzdesi — partilerin returnPct ortalaması DEĞİL. */
  weightedReturnPct: number;
}

/** Bir enstrümanın tüm partilerinin toplamı — Holding'in türetilmiş alanlarının tek kaynağı. */
export function holdingTotals(lots: HoldingLot[], currentUnitPrice: number): HoldingTotals {
  const totalQuantity = lots.reduce((sum, lot) => sum + lot.quantity, 0);
  const totalValue = lots.reduce((sum, lot) => sum + lotValue(lot, currentUnitPrice), 0);
  const totalCost = lots.reduce((sum, lot) => sum + lot.unitCost * lot.quantity, 0);
  const totalPnl = totalValue - totalCost;
  const weightedReturnPct = totalCost === 0 ? 0 : (totalPnl / totalCost) * 100;
  return { totalQuantity, totalValue, totalCost, totalPnl, weightedReturnPct };
}
