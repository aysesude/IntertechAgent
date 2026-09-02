import { describe, expect, it, vi } from "vitest";

/**
 * Hızlı Özet ucunun İSTEMCİ ZAMAN AŞIMI.
 *
 * "Özet alınamadı" hatasının gerçek sebebi buydu (ölçüldü, 2 Eylül 2026):
 * `apiGet`in varsayılanı 8 saniye — diğer uçlar tek bir DB sorgusu olduğu
 * için makul, ama bu uç beş MCP tool'u + bir LLM turu çalıştırıyor ve
 * 10-30 saniye sürüyor. Tarayıcı 8. saniyede isteği iptal edip hata
 * gösteriyordu, backend'in cevabı yolda olsa bile.
 *
 * Sunucu tarafındaki sınır 60 sn; buradaki değer ondan BÜYÜK olmalı, aksi
 * hâlde istemci önce vazgeçer ve kullanıcı sunucunun dürüst "üretilemedi"
 * yanıtı yerine genel bir bağlantı hatası görür.
 */

const apiGet = vi.fn().mockResolvedValue({ user_id: "u", generated_at: "", cards: [] });

vi.mock("./client", () => ({ apiGet: (...a: unknown[]) => apiGet(...a) }));

const { fetchInsightCards } = await import("./insight");

/** `backend/app/api/insight.py::_ZAMAN_ASIMI_SANIYE` */
const SUNUCU_SINIRI_MS = 60_000;

describe("fetchInsightCards", () => {
  it("SUNUCU SINIRINDAN uzun bir zaman aşımı geçirir", () => {
    fetchInsightCards("kullanici-1");

    const [yol, secenekler] = apiGet.mock.calls[0] as [string, { timeoutMs?: number }];
    expect(yol).toBe("/api/insight/kullanici-1");
    expect(secenekler?.timeoutMs).toBeGreaterThan(SUNUCU_SINIRI_MS);
  });
});
