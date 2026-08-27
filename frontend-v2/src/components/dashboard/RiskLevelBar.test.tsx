import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RiskLevelBar, RISK_SCALE_MAX } from "./RiskLevelBar";

/**
 * Göstergenin iki işi var: doğru sayıyı yazmak ve dolan parçanın uzunluğunu
 * kademeyle orantılı tutmak. İkincisi görsel gibi görünse de yanlış olduğunda
 * kullanıcı yanlış bir risk okur — bu yüzden genişlik doğrudan sınanıyor.
 */
describe("RiskLevelBar", () => {
  it("kademeyi yazar ve erişilebilir etiket üretir", () => {
    render(<RiskLevelBar level={6} />);

    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAccessibleName(
      `Risk kademesi ${RISK_SCALE_MAX} üzerinden 6`,
    );
  });

  it("risk hesaplanamadıysa hiçbir şey çizmez", () => {
    const { container } = render(<RiskLevelBar level={null} />);
    // Yeterli fiyat geçmişi yoksa risk UYDURULMAZ (AK 2.7); boş bir çubuk
    // "risk sıfır" diye okunurdu.
    expect(container).toBeEmptyDOMElement();
  });

  it("dolan parça kademeyle orantılı", () => {
    const genislik = (level: number) => {
      const { container } = render(<RiskLevelBar level={level} />);
      const dolu = container.querySelector<HTMLElement>("[role='img'] > div > div");
      return dolu?.style.width;
    };

    expect(genislik(7)).toBe("100%");
    expect(genislik(1)).toBe(`${(1 / 7) * 100}%`);
  });

  it("renk şeridi çubuğun TAMAMINA yayılır, dolan parçaya sıkışmaz", () => {
    // Şerit dolan parçaya sığdırılsaydı 1. kademe de 7. kademe de kendi
    // içinde yeşilden kırmızıya giderdi ve renk hiçbir şey anlatmazdı.
    const { container } = render(<RiskLevelBar level={1} />);
    const serit = container.querySelector<HTMLElement>("[role='img'] > div > div > div");

    expect(serit?.style.width).toBe(`${7 * 100}%`);
  });

  it("aralık dışı değer sınıra çekilir", () => {
    // Backend 1-7 dışına çıkmamalı ama çıkarsa gösterge çökmemeli
    // (zarif düşüş); 9 kademelik bir çubuk çizmek daha kötü olurdu.
    render(<RiskLevelBar level={99} />);
    expect(screen.getByText(String(RISK_SCALE_MAX))).toBeInTheDocument();
  });
});
