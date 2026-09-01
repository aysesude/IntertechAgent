import { apiGet } from "./client";

/**
 * "Hızlı Özet" panelinin dört kartı.
 *
 * `backend/app/schemas/insight.py` ile birebir eşleşir. Kartları üreten
 * Özet Ajanı'nın sözleşmesi için `agents/summary_agent.py` docstring'i:
 * ajan kendi sayısını üretemez, ürettiği metindeki her sayı deterministik
 * bloğa karşı doğrulanır.
 */

/** Akordeon sırası bu id'lere göre kurulur. */
export type InsightCardId = "genel" | "portfoy" | "piyasa" | "risk";

export interface ApiInsightCard {
  id: InsightCardId;
  title: string;
  body: string;
  /**
   * Kartın metni LLM'den DEĞİL, deterministik özetten geliyor: ya sayı
   * doğrulaması başarısız oldu ya da veri kaynağı düştü. Kart yine
   * gösterilir (zarif düşüş) ama arayüz bunu belirtmelidir — cilalı bir
   * cümle beklerken ham satırlar gören kullanıcı, sebebini bilmeli.
   */
  degraded: boolean;
}

export interface ApiInsightCards {
  user_id: string;
  generated_at: string;
  cards: ApiInsightCard[];
}

/**
 * Panel HER AÇILIŞTA yeniden üretilir; önbellek YOK (ürün kararı, 1 Eylül
 * 2026: paneli açmak yenilemek demek). Bu yüzden burada da, hook'ta da
 * saklama katmanı bulunmuyor — diğer ekranlarda olan modül düzeyi önbellek
 * kalıbı bilerek uygulanmadı.
 */
export function fetchInsightCards(userId: string): Promise<ApiInsightCards> {
  return apiGet<ApiInsightCards>(`/api/insight/${userId}`);
}
