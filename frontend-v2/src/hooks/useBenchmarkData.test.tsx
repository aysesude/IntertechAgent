import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiBenchmarkComparison } from "@/api/portfolio";

/**
 * Kıyaslama kartının veri kancası.
 *
 * Asıl mesele dönem değişimi: `useApiResource` yalnızca `refetch` ile
 * yeniden yüklüyor, `fetcher` değişince değil. O kancayla dönem düğmesine
 * basmak HİÇ istek atmaz ve kullanıcı yanlış dönemin rakamlarına bakardı —
 * grafik değişmediği için de fark etmesi zor olurdu.
 */

const fetchBenchmark = vi.fn();

vi.mock("@/api/portfolio", () => ({
  fetchBenchmark: (...a: unknown[]) => fetchBenchmark(...a),
}));

vi.mock("@/api/client", () => ({ isApiConfigured: true }));

vi.mock("@/auth/AuthContext", () => ({
  useCurrentUserId: () => "user-1",
}));

const { useBenchmarkData } = await import("./useBenchmarkData");

function yanit(ustuneYaz: Partial<ApiBenchmarkComparison> = {}): ApiBenchmarkComparison {
  return {
    user_id: "user-1",
    window: "12m",
    start_date: "2025-09-08",
    end_date: "2026-08-26",
    truncated_to_inception: false,
    portfolio_return_percent: 10,
    benchmarks: [{ symbol: "XU100", name: "BIST 100", return_percent: 5 }],
    excluded_symbols: [],
    ...ustuneYaz,
  };
}

function Sonda({ pencere }: { pencere: "1m" | "12m" }) {
  const { data, loading, periodLoading, error } = useBenchmarkData(pencere);
  return (
    <div>
      <span data-testid="pencere">{data?.window ?? "-"}</span>
      <span data-testid="getiri">{data?.portfolio_return_percent ?? "-"}</span>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="donem">{String(periodLoading)}</span>
      <span data-testid="hata">{error ?? "-"}</span>
    </div>
  );
}

describe("useBenchmarkData", () => {
  beforeEach(() => {
    fetchBenchmark.mockReset();
  });

  it("seçili pencereyle istek atar", async () => {
    fetchBenchmark.mockResolvedValue(yanit());

    render(<Sonda pencere="12m" />);

    await waitFor(() => expect(screen.getByTestId("pencere")).toHaveTextContent("12m"));
    expect(fetchBenchmark).toHaveBeenCalledWith("user-1", "12m");
  });

  it("dönem değişince YENİDEN istek atar", async () => {
    fetchBenchmark.mockImplementation((_u: string, w: string) =>
      Promise.resolve(yanit({ window: w as "1m" | "12m", portfolio_return_percent: w === "1m" ? 3 : 10 })),
    );

    const { rerender } = render(<Sonda pencere="12m" />);
    await waitFor(() => expect(screen.getByTestId("getiri")).toHaveTextContent("10"));

    rerender(<Sonda pencere="1m" />);

    await waitFor(() => expect(screen.getByTestId("getiri")).toHaveTextContent("3"));
    expect(fetchBenchmark).toHaveBeenCalledTimes(2);
    expect(fetchBenchmark).toHaveBeenLastCalledWith("user-1", "1m");
  });

  it("dönem yüklenirken ÖNCEKİ veri ekranda kalır", async () => {
    let cozumle: ((v: ApiBenchmarkComparison) => void) | null = null;
    fetchBenchmark
      .mockResolvedValueOnce(yanit({ portfolio_return_percent: 10 }))
      .mockImplementationOnce(() => new Promise((r) => (cozumle = r)));

    const { rerender } = render(<Sonda pencere="12m" />);
    await waitFor(() => expect(screen.getByTestId("getiri")).toHaveTextContent("10"));

    rerender(<Sonda pencere="1m" />);

    // Kart DOM'dan kalkmasın diye eski seri duruyor; ilk yükleme bayrağı
    // değil dönem bayrağı yanıyor.
    await waitFor(() => expect(screen.getByTestId("donem")).toHaveTextContent("true"));
    expect(screen.getByTestId("getiri")).toHaveTextContent("10");
    expect(screen.getByTestId("loading")).toHaveTextContent("false");

    cozumle!(yanit({ window: "1m", portfolio_return_percent: 3 }));
    await waitFor(() => expect(screen.getByTestId("getiri")).toHaveTextContent("3"));
  });

  it("hata olunca eldeki veriyi SİLMEZ ama hatayı gösterir", async () => {
    fetchBenchmark
      .mockResolvedValueOnce(yanit({ portfolio_return_percent: 10 }))
      .mockRejectedValueOnce(new Error("sunucu düştü"));

    const { rerender } = render(<Sonda pencere="12m" />);
    await waitFor(() => expect(screen.getByTestId("getiri")).toHaveTextContent("10"));

    rerender(<Sonda pencere="1m" />);

    await waitFor(() => expect(screen.getByTestId("hata")).toHaveTextContent("sunucu düştü"));
    // Eski dönemin verisi ama GERÇEK; silip boş kart göstermek kullanıcıyı
    // "veri yok" sanısına düşürürdü.
    expect(screen.getByTestId("getiri")).toHaveTextContent("10");
  });
});
