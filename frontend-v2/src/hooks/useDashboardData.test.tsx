import { render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiPerformanceResult, ApiPortfolioSummary } from "@/api/portfolio";
import type { RangeKey } from "@/types/finance";

/**
 * useDashboardData testleri.
 *
 * Buradaki asıl mesele görsel: dönem düğmesine basınca grafik kartı DOM'dan
 * kalkıyor, sayfa düzeni çöküyor ve veri gelince kart yeniden beliriyordu.
 * Sebep, adapter'ın yalnızca SEÇİLİ dönemi doldurması — dönem değişince
 * `performance[range]` bir anlığına `undefined` oluyordu.
 *
 * İkinci ve daha sinsi hâli: türetme o anda mock veriye düşüyor, yani tüm
 * dashboard (özet kartları, dağılım, işlemler) bir kare boyunca TASARIM
 * VERİSİ gösteriyordu. Ekranda rakam var ve makul görünüyor — gözle
 * yakalanması çok zor.
 */

const fetchPortfolioSummary = vi.fn();
const fetchPerformance = vi.fn();
const fetchHoldings = vi.fn();
const fetchTransactions = vi.fn();

vi.mock("@/api/portfolio", () => ({
  fetchPortfolioSummary: (...a: unknown[]) => fetchPortfolioSummary(...a),
  fetchPerformance: (...a: unknown[]) => fetchPerformance(...a),
  fetchHoldings: (...a: unknown[]) => fetchHoldings(...a),
  fetchTransactions: (...a: unknown[]) => fetchTransactions(...a),
}));
// Risk ucu opsiyonel: düşerse dashboard yine çizilir. Bu testler dönem
// geçişine odaklandığı için risk hep null döndürülüyor.
const fetchRiskAssessment = vi.fn();
vi.mock("@/api/risk", () => ({
  fetchRiskAssessment: (...a: unknown[]) => fetchRiskAssessment(...a),
}));
vi.mock("@/api/client", () => ({ isApiConfigured: true }));
vi.mock("@/auth/AuthContext", () => ({ useCurrentUserId: () => "kullanici-1" }));
vi.mock("@/context/ThemeContext", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }));

const { useDashboardData } = await import("./useDashboardData");

const OZET: ApiPortfolioSummary = {
  user_id: "kullanici-1",
  as_of: "2026-08-20",
  oldest_price_date: "2026-08-20",
  total_value: 1_569_468.64,
  total_cost_basis: 1_259_878,
  net_invested: 1_400_000,
  total_gain_loss: { amount: 169_468.64, percent: 12.1 },
  allocation: [{ asset_class: "stock", value: 130_000, percent: 100 }],
  holdings_count: 8,
};

function performans(window: string, deger: number): ApiPerformanceResult {
  return {
    user_id: "kullanici-1",
    as_of: "2026-08-20",
    window: window as ApiPerformanceResult["window"],
    granularity: "daily",
    inception: "2025-08-05",
    truncated_to_inception: false,
    series: [{ date: "2026-05-22", value_try: deger, invested_try: 1_400_000 }],
    summary: {
      start_value: deger,
      end_value: deger,
      change_amount: 0,
      change_percent: 4.14,
      realized_pnl: 0,
      unrealized_pnl: 0,
      changes: { daily: 0.19, weekly: null, monthly: null },
    },
  };
}

/** Dönem düğmelerini ve gözlemlediğimiz alanları basan yardımcı bileşen. */
function Panel() {
  const [range, setRange] = useState<RangeKey>("1Y");
  const { data, chartRange, rangeLoading, isDemoData } = useDashboardData(range);
  return (
    <div>
      <span data-testid="kart-var">{chartRange === null ? "YOK" : "VAR"}</span>
      <span data-testid="seri-degeri">{chartRange?.points[0]?.portfolio ?? "-"}</span>
      <span data-testid="toplam">{data.summary.totalValue}</span>
      <span data-testid="yukleniyor">{String(rangeLoading)}</span>
      <span data-testid="demo">{String(isDemoData)}</span>
      <button onClick={() => setRange("3A")}>3A</button>
      <button onClick={() => setRange("1Y")}>1Y</button>
    </div>
  );
}

beforeEach(() => {
  fetchPortfolioSummary.mockReset().mockResolvedValue(OZET);
  fetchHoldings.mockReset().mockResolvedValue(null);
  fetchTransactions.mockReset().mockResolvedValue(null);
  fetchRiskAssessment.mockReset().mockResolvedValue(null);
  fetchPerformance.mockReset();
});

describe("dönem değişimi", () => {
  it("kart DOM'dan KALKMAZ — yeni dönem yüklenirken eski seri gösterilir", async () => {
    // GERİLEME TESTİ: bildirilen hata tam olarak buydu ("kart tamamen kapanıp
    // geri geliyor, düzen bozuluyor").
    fetchPerformance.mockResolvedValueOnce(performans("12m", 1_000));

    render(<Panel />);
    await waitFor(() => expect(screen.getByTestId("kart-var")).toHaveTextContent("VAR"));

    // 3A isteği ÇÖZÜLMEDEN bekletiliyor: geçiş anını yakalamak için.
    let cozumle: ((v: ApiPerformanceResult) => void) | undefined;
    fetchPerformance.mockImplementationOnce(
      () => new Promise<ApiPerformanceResult>((resolve) => (cozumle = resolve)),
    );

    await act(async () => {
      screen.getByText("3A").click();
    });

    // Yükleme sürerken kart hâlâ DOM'da ve eski seriyi gösteriyor.
    expect(screen.getByTestId("kart-var")).toHaveTextContent("VAR");
    expect(screen.getByTestId("seri-degeri")).toHaveTextContent("1000");
    expect(screen.getByTestId("yukleniyor")).toHaveTextContent("true");

    await act(async () => {
      cozumle?.(performans("3m", 2_000));
    });

    await waitFor(() => expect(screen.getByTestId("seri-degeri")).toHaveTextContent("2000"));
  });

  it("yeni dönem yüklenirken ekran MOCK VERİYE düşmez", async () => {
    // Türetme `performansCache[range]` boş olunca mockDashboard döndürüyordu;
    // yani özet kartları bir kare boyunca tasarım verisi gösteriyordu.
    fetchPerformance.mockResolvedValueOnce(performans("12m", 1_000));

    render(<Panel />);
    await waitFor(() => expect(screen.getByTestId("toplam")).toHaveTextContent("1569468.64"));

    fetchPerformance.mockImplementationOnce(() => new Promise<ApiPerformanceResult>(() => {}));
    await act(async () => {
      screen.getByText("3A").click();
    });

    // Gerçek toplam korunmalı; mock verinin toplamı bambaşka bir sayı.
    expect(screen.getByTestId("toplam")).toHaveTextContent("1569468.64");
    expect(screen.getByTestId("demo")).toHaveTextContent("false");
  });

  it("dönem değişince YALNIZCA performans ucu yeniden çağrılır", async () => {
    // Özet/varlıklar/işlemler dönemden bağımsız; dördünü birden çekmek hem
    // gereksiz hem de bekleme penceresini uzatıyordu.
    fetchPerformance.mockResolvedValue(performans("12m", 1_000));

    render(<Panel />);
    await waitFor(() => expect(screen.getByTestId("kart-var")).toHaveTextContent("VAR"));
    expect(fetchPortfolioSummary).toHaveBeenCalledTimes(1);

    await act(async () => {
      screen.getByText("3A").click();
    });
    await waitFor(() => expect(fetchPerformance).toHaveBeenCalledTimes(2));

    expect(fetchPortfolioSummary).toHaveBeenCalledTimes(1);
    expect(fetchHoldings).toHaveBeenCalledTimes(1);
    expect(fetchTransactions).toHaveBeenCalledTimes(1);
  });

  it("önceden yüklenmiş döneme dönmek AĞA ÇIKMAZ", async () => {
    fetchPerformance
      .mockResolvedValueOnce(performans("12m", 1_000))
      .mockResolvedValueOnce(performans("3m", 2_000));

    render(<Panel />);
    await waitFor(() => expect(screen.getByTestId("kart-var")).toHaveTextContent("VAR"));

    await act(async () => {
      screen.getByText("3A").click();
    });
    await waitFor(() => expect(screen.getByTestId("seri-degeri")).toHaveTextContent("2000"));
    expect(fetchPerformance).toHaveBeenCalledTimes(2);

    await act(async () => {
      screen.getByText("1Y").click();
    });

    // Önbellekten geldi: yeni istek yok ve seri anında değişti.
    await waitFor(() => expect(screen.getByTestId("seri-degeri")).toHaveTextContent("1000"));
    expect(fetchPerformance).toHaveBeenCalledTimes(2);
  });

  it("aynı dönem için MÜKERRER istek göndermez", async () => {
    // İstek uçuştayken başka bir state değişimi effect'i tetiklerse ikinci
    // bir istek daha gidiyordu.
    fetchPerformance.mockResolvedValue(performans("12m", 1_000));

    render(<Panel />);
    await waitFor(() => expect(screen.getByTestId("kart-var")).toHaveTextContent("VAR"));

    expect(fetchPerformance).toHaveBeenCalledTimes(1);
  });
});
