import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Hızlı Özet kancası.
 *
 * İki davranış kritik:
 *   1. Panel KAPALIYKEN istek atılmaz — sayfa açılışında otomatik üretim,
 *      her sayfa geçişine bir LLM turu eklerdi (≤5 sn hedefi).
 *   2. Panel kapanınca kartlar temizlenir — bir sonraki açılışta ESKİ özet
 *      bir an görünmemeli; üstünde tarih yazmayan eski bir metin güncel
 *      sanılır.
 */

const fetchInsightCards = vi.fn();

vi.mock("@/api/insight", () => ({
  fetchInsightCards: (...a: unknown[]) => fetchInsightCards(...a),
}));

vi.mock("@/api/client", () => ({ isApiConfigured: true }));

vi.mock("@/auth/AuthContext", () => ({
  useCurrentUserId: () => "kullanici-1",
}));

const { useInsightData } = await import("./useInsightData");

const KARTLAR = [{ id: "genel", title: "Genel Durum", body: "gövde", degraded: false }];

beforeEach(() => {
  fetchInsightCards.mockReset();
  fetchInsightCards.mockResolvedValue({
    user_id: "kullanici-1",
    generated_at: "2026-09-01T20:00:00Z",
    cards: KARTLAR,
  });
});

describe("useInsightData", () => {
  it("panel KAPALIYKEN istek ATILMAZ", () => {
    renderHook(() => useInsightData(false));

    expect(fetchInsightCards).not.toHaveBeenCalled();
  });

  it("panel açılınca kartları yükler", async () => {
    const { result } = renderHook(() => useInsightData(true));

    await waitFor(() => expect(result.current.cards).toHaveLength(1));
    expect(fetchInsightCards).toHaveBeenCalledWith("kullanici-1");
    expect(result.current.error).toBeNull();
  });

  it("panel kapanınca kartlar TEMİZLENİR", async () => {
    const { result, rerender } = renderHook(({ acik }) => useInsightData(acik), {
      initialProps: { acik: true },
    });
    await waitFor(() => expect(result.current.cards).toHaveLength(1));

    rerender({ acik: false });

    expect(result.current.cards).toHaveLength(0);
  });

  it("istek düşerse MOCK'A DÜŞMEZ, hata söyler", async () => {
    // Uydurma bir "özet" göstermek, kartların taşıdığı tek değeri
    // (ölçülmüş veriye dayanmak) yok ederdi.
    fetchInsightCards.mockRejectedValue(new Error("kopuk"));

    const { result } = renderHook(() => useInsightData(true));

    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.cards).toHaveLength(0);
  });
});
