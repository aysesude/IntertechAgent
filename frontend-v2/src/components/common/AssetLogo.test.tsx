import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AssetLogo } from "./AssetLogo";

/**
 * Logo bileşeni.
 *
 * En önemli değişmez YEDEĞİN ÇALIŞMASI: evrenin 141 varlığının 21'inde logo
 * yok (fon, döviz, maden) ve bunlar uçtan 404 alıyor. Yedek bozulursa o
 * satırlarda kırık görsel ikonu çıkar — sessiz değil, çirkin bir hata.
 */

function gorsel(): HTMLImageElement {
  const el = document.querySelector("img");
  if (!el) throw new Error("img yok");
  return el as HTMLImageElement;
}

describe("AssetLogo", () => {
  it("logo ucuna sembolle gider", () => {
    render(<AssetLogo symbol="THYAO" />);
    expect(gorsel().getAttribute("src")).toContain("/api/logos/THYAO");
  });

  it("404 gelince HARF ROZETİNE düşer", () => {
    // Uç, logosu olmayan sembolde bilerek 404 dönüyor; boş görsel döndürmek
    // eksik logoyu görünmez bir kusura çevirirdi.
    render(<AssetLogo symbol="USDTRY" />);

    fireEvent.error(gorsel());

    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("US")).toBeInTheDocument();
  });

  it("rozet rengi SEMBOLE bağlı, çağrıya değil", () => {
    // Rastgele seçilseydi aynı hisse portföy tablosunda mavi, Al/Sat
    // listesinde yeşil görünür ve göz onu iki ayrı şey sanardı.
    const renkAl = (sembol: string) => {
      const { container, unmount } = render(<AssetLogo symbol={sembol} />);
      fireEvent.error(container.querySelector("img")!);
      const renk = container.querySelector("span")!.style.background;
      unmount();
      return renk;
    };

    expect(renkAl("XAUTRY")).toBe(renkAl("XAUTRY"));
  });

  it("yuvarlak çiziliyor", () => {
    // Ölçüldü: logoların tamamı 60x60 kare ve zemini tam dolu, dolayısıyla
    // daire içine kırpmak yalnızca köşeleri alıyor.
    render(<AssetLogo symbol="THYAO" />);
    expect(gorsel().className).toContain("rounded-full");
  });

  it("boyut hem görselde hem rozette uygulanır", () => {
    const { container } = render(<AssetLogo symbol="THYAO" size={40} />);
    expect(gorsel().style.width).toBe("40px");

    fireEvent.error(gorsel());
    expect(container.querySelector("span")!.style.width).toBe("40px");
  });

  it("ekran okuyucudan gizli", () => {
    // Sembol zaten satırda yazılı; iki kez okutmanın faydası yok.
    render(<AssetLogo symbol="THYAO" />);
    expect(gorsel().getAttribute("aria-hidden")).toBe("true");
  });
});
