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
 * İSTEMCİ ZAMAN AŞIMI 70 SANİYE — `apiGet`in 8 sn'lik varsayılanı BU UÇ İÇİN
 * YANLIŞTI ve "özet alınamadı" hatasının gerçek sebebiydi (ölçüldü, 2 Eylül
 * 2026).
 *
 * Diğer uçlar tek bir DB sorgusu; 8 sn onlar için makul bir üst sınır. Bu uç
 * ise beş MCP tool'u + bir LLM turu çalıştırıyor ve 10-30 saniye sürüyor.
 * Tarayıcı 8. saniyede isteği iptal edip hata gösteriyordu — backend'in
 * cevabı yolda olsa bile.
 *
 * Sunucu tarafındaki sınır 60 sn (`backend/app/api/insight.py`). Buradaki
 * değer ondan BÜYÜK olmalı: aksi hâlde istemci önce vazgeçer ve kullanıcı,
 * sunucunun dürüst "üretilemedi" yanıtı yerine genel bir bağlantı hatası
 * görür. 70 = 60 + ağ payı.
 */
const ZAMAN_ASIMI_MS = 70_000;

/**
 * Panel HER AÇILIŞTA yeniden üretilir; önbellek YOK (ürün kararı, 1 Eylül
 * 2026: paneli açmak yenilemek demek). Bu yüzden burada da, hook'ta da
 * saklama katmanı bulunmuyor — diğer ekranlarda olan modül düzeyi önbellek
 * kalıbı bilerek uygulanmadı.
 */
export function fetchInsightCards(userId: string): Promise<ApiInsightCards> {
  return apiGet<ApiInsightCards>(`/api/insight/${userId}`, { timeoutMs: ZAMAN_ASIMI_MS });
}
