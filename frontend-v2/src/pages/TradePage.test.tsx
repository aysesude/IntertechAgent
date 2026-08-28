import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiTradableAsset, ApiTradableList } from "@/api/trade";

/**
 * Al/Sat ekranı.
 *
 * Buradaki değişmezlerin çoğu "yanlış şeyi gizlememe" üzerine: kilitli
 * varlığın sebebi görünmeli, satış tarafında kilit UYGULANMAMALI, işlemden
 * sonra portföy önbellekleri boşalmalı.
 */

const fetchTradableAssets = vi.fn();
const previewTrade = vi.fn();
const executeTrade = vi.fn();
const depositCash = vi.fn();

vi.mock("@/api/trade", () => ({
  fetchTradableAssets: (...a: unknown[]) => fetchTradableAssets(...a),
  previewTrade: (...a: unknown[]) => previewTrade(...a),
  executeTrade: (...a: unknown[]) => executeTrade(...a),
  depositCash: (...a: unknown[]) => depositCash(...a),
}));

vi.mock("@/api/client", () => ({
  isApiConfigured: true,
  getApiBaseUrl: () => "http://test",
}));

vi.mock("@/auth/AuthContext", () => ({
  useCurrentUserId: () => "user-1",
}));

const portfolioSifirla = vi.fn();
const dashboardSifirla = vi.fn();
vi.mock("@/hooks/usePortfolioData", () => ({
  __portfolioOnbelleginiSifirla: () => portfolioSifirla(),
}));
vi.mock("@/hooks/useDashboardData", () => ({
  __dashboardOnbelleginiSifirla: () => dashboardSifirla(),
}));

const { TradePage } = await import("./TradePage");

function varlik(ustuneYaz: Partial<ApiTradableAsset> = {}): ApiTradableAsset {
  return {
    symbol: "THYAO",
    name: "Türk Hava Yolları",
    asset_class: "stock",
    currency: "TRY",
    risk_level: 5,
    price: 305.5,
    price_date: "2026-08-27",
    price_source: "yfinance",
    price_stale: false,
    can_buy: true,
    block_reason: null,
    held_quantity: 0,
    quantity_step: 1,
    ...ustuneYaz,
  };
}

function liste(assets: ApiTradableAsset[]): ApiTradableList {
  return { user_id: "user-1", survey_score: 5, cash_balance: 100000, assets };
}

describe("TradePage", () => {
  beforeEach(() => {
    fetchTradableAssets.mockReset();
    previewTrade.mockReset();
    executeTrade.mockReset();
    depositCash.mockReset();
    portfolioSifirla.mockReset();
    dashboardSifirla.mockReset();
  });

  it("kilitli varlığın SEBEBİNİ gösterir", async () => {
    // Sessizce elemek ya da sebepsiz kilitlemek, kullanıcıyı hatayı kendinde
    // aramaya iter.
    fetchTradableAssets.mockResolvedValue(
      liste([
        varlik({
          symbol: "AAPL",
          name: "Apple",
          risk_level: 6,
          can_buy: false,
          block_reason: "Bu varlığın risk seviyesi 6, sizin anket puanınız 5.",
        }),
      ]),
    );

    render(<TradePage />);

    expect(await screen.findByText(/risk seviyesi 6/)).toBeInTheDocument();
  });

  it("SAT sekmesinde kilit uygulanmaz", async () => {
    // Elindeki uyumsuz varlıktan çıkışın tek yolu satmak; satışı da
    // engellemek kullanıcıyı uyumsuz pozisyonda kilitler.
    fetchTradableAssets.mockResolvedValue(
      liste([
        varlik({
          symbol: "AAPL",
          name: "Apple",
          can_buy: false,
          block_reason: "Profilinize uymuyor.",
          held_quantity: 3,
        }),
      ]),
    );

    render(<TradePage />);
    fireEvent.click(await screen.findByRole("button", { name: "Sat" }));

    const satir = screen.getByRole("button", { name: /Apple/ });
    expect(satir).not.toBeDisabled();
  });

  it("SAT sekmesi yalnızca ELDEKİ pozisyonları listeler", async () => {
    // Satılamayacak varlığı listeleyip tıklanınca hata vermek daha kötü.
    fetchTradableAssets.mockResolvedValue(
      liste([
        varlik({ symbol: "THYAO", name: "Türk Hava Yolları", held_quantity: 0 }),
        varlik({ symbol: "AKBNK", name: "Akbank", held_quantity: 5 }),
      ]),
    );

    render(<TradePage />);
    fireEvent.click(await screen.findByRole("button", { name: "Sat" }));

    expect(screen.getByRole("button", { name: /Akbank/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Türk Hava/ })).not.toBeInTheDocument();
  });

  it("işlemden sonra portföy VE dashboard önbellekleri boşalır", async () => {
    // Boşalmazsa kullanıcı portföye döndüğünde az önce aldığı varlığı
    // görmez ve işlemin çalışmadığını sanar — bu ekranın varlık sebebi tam
    // da etkiyi göstermek.
    fetchTradableAssets.mockResolvedValue(liste([varlik()]));
    depositCash.mockResolvedValue({ cash_balance: 200000 });

    render(<TradePage />);
    fireEvent.click(await screen.findByRole("button", { name: /Para Yatır/ }));

    await waitFor(() => expect(portfolioSifirla).toHaveBeenCalled());
    expect(dashboardSifirla).toHaveBeenCalled();
  });

  it("nakit bakiyesi üstte görünür", async () => {
    fetchTradableAssets.mockResolvedValue(liste([varlik()]));

    render(<TradePage />);

    expect(await screen.findByText(/100\.000/)).toBeInTheDocument();
  });

  it("liste alınamazsa hata gösterilir, sessizce boş kalmaz", async () => {
    fetchTradableAssets.mockRejectedValue(new Error("sunucu düştü"));

    render(<TradePage />);

    expect(await screen.findByText(/sunucu düştü/)).toBeInTheDocument();
  });

  it("arama sembol ve isimde çalışır", async () => {
    fetchTradableAssets.mockResolvedValue(
      liste([
        varlik({ symbol: "THYAO", name: "Türk Hava Yolları" }),
        varlik({ symbol: "AKBNK", name: "Akbank" }),
      ]),
    );

    render(<TradePage />);
    await screen.findByRole("button", { name: /Akbank/ });

    fireEvent.change(screen.getByPlaceholderText(/ara/i), { target: { value: "akb" } });

    expect(screen.getByRole("button", { name: /Akbank/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Türk Hava/ })).not.toBeInTheDocument();
  });
});
