import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * `useApiResource` testleri.
 *
 * Buradaki asıl mesele estetik değil DÜRÜSTLÜK. Taşınan kodda hook, istek
 * hata verince sessizce mock veriye düşüyor ve sayfalar `error` alanını hiç
 * okumuyordu — yani backend düştüğünde ekranda uydurma ₺ rakamları gerçekmiş
 * gibi görünüyordu. Bir finans ürününde kabul edilemez (CLAUDE.md §4).
 *
 * Aşağıdaki testler o sözleşmeyi kilitliyor: veri sunucudan gelmediyse
 * `isDemoData` HER ZAMAN true olmalı, hata varsa `error` HER ZAMAN dolu.
 */

const isApiConfigured = vi.hoisted(() => ({ value: true }));

vi.mock("@/api/client", () => ({
  get isApiConfigured() {
    return isApiConfigured.value;
  },
}));

const { useApiResource } = await import("./useApiResource");

const MOCK = { deger: "tasarim-verisi" };
const CANLI = { deger: "sunucudan" };

function Gosterge({ fetcher }: { fetcher: (() => Promise<typeof MOCK>) | null }) {
  const { data, loading, error, isLive, isDemoData } = useApiResource(fetcher, MOCK);
  return (
    <div>
      <span data-testid="deger">{data.deger}</span>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="error">{error ?? "-"}</span>
      <span data-testid="isLive">{String(isLive)}</span>
      <span data-testid="isDemoData">{String(isDemoData)}</span>
    </div>
  );
}

beforeEach(() => {
  isApiConfigured.value = true;
});

describe("henüz bağlanmamış ekran (fetcher = null)", () => {
  it("istek ATMAZ ve veriyi demo olarak işaretler", async () => {
    render(<Gosterge fetcher={null} />);

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("deger")).toHaveTextContent("tasarim-verisi");
    // Var olmayan bir uca boşa istek atıp 404 yiyerek mock'a "düşmek" ile
    // bilerek tasarım verisi göstermek aynı şey değil; ikincisi bilinçli.
    expect(screen.getByTestId("isDemoData")).toHaveTextContent("true");
    expect(screen.getByTestId("isLive")).toHaveTextContent("false");
    expect(screen.getByTestId("error")).toHaveTextContent("-");
  });
});

describe("bağlanmış ekran", () => {
  it("başarılı istekte canlı veriyi gösterir ve demo işaretini kaldırır", async () => {
    const fetcher = vi.fn().mockResolvedValue(CANLI);

    render(<Gosterge fetcher={fetcher} />);

    await waitFor(() => expect(screen.getByTestId("deger")).toHaveTextContent("sunucudan"));
    expect(screen.getByTestId("isLive")).toHaveTextContent("true");
    expect(screen.getByTestId("isDemoData")).toHaveTextContent("false");
    expect(screen.getByTestId("error")).toHaveTextContent("-");
  });

  it("hata durumunda error DOLU ve veri demo olarak işaretli olur", async () => {
    // Gerileme testi: eskiden hata sessizce yutuluyor, ekran hiçbir şey
    // olmamış gibi mock gösteriyordu. Bağlanmış bir ekran artık `error`ı
    // göstermek zorunda; bu test o alanın gerçekten dolduğunu garanti eder.
    const fetcher = vi.fn().mockRejectedValue(new Error("Sunucuya ulaşılamadı."));

    render(<Gosterge fetcher={fetcher} />);

    await waitFor(() =>
      expect(screen.getByTestId("error")).toHaveTextContent("Sunucuya ulaşılamadı."),
    );
    expect(screen.getByTestId("isDemoData")).toHaveTextContent("true");
    expect(screen.getByTestId("isLive")).toHaveTextContent("false");
    expect(screen.getByTestId("deger")).toHaveTextContent("tasarim-verisi");
  });

  it("hata bir Error değilse bile anlaşılır bir metin verir", async () => {
    const fetcher = vi.fn().mockRejectedValue("düz metin");

    render(<Gosterge fetcher={fetcher} />);

    await waitFor(() => expect(screen.getByTestId("error")).toHaveTextContent("Veri alınamadı."));
  });
});

describe("API adresi tanımlı değilken", () => {
  it("fetcher verilse bile istek atmaz, demo veriyle çalışır", async () => {
    // Yerel kurulumda backend olmadan tasarım incelemesi yapılabilsin diye.
    isApiConfigured.value = false;
    const fetcher = vi.fn().mockResolvedValue(CANLI);

    render(<Gosterge fetcher={fetcher} />);

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(fetcher).not.toHaveBeenCalled();
    expect(screen.getByTestId("isDemoData")).toHaveTextContent("true");
  });
});
