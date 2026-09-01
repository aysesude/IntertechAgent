import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ApiInsightCard } from "@/api/insight";
import { InsightCards } from "./InsightCards";

/**
 * Akordeon kartlar.
 *
 * Kritik davranış: TIKLAMAYLA açılır, hover ile değil. Hover ile açmak fare
 * kartlara doğru giderken içeriği değiştirir, dokunmatikte hiç çalışmaz ve
 * kayıtlı demo videolarında kartlar kendiliğinden açılıyormuş gibi görünür.
 */

const KARTLAR: ApiInsightCard[] = [
  { id: "genel", title: "Genel Durum", body: "Genel gövde.", degraded: false },
  { id: "portfoy", title: "Portföyünüz", body: "Portföy gövdesi.", degraded: false },
  { id: "piyasa", title: "Piyasa", body: "Piyasa gövdesi.", degraded: false },
  { id: "risk", title: "Risk", body: "Risk gövdesi.", degraded: true },
];

describe("InsightCards", () => {
  it("açılışta BULUNULAN SAYFANIN kartı geniş gelir", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="risk" />);

    // Yalnızca açık kartın gövdesi basılır.
    expect(screen.getByText("Risk gövdesi.")).toBeInTheDocument();
    expect(screen.queryByText("Genel gövde.")).not.toBeInTheDocument();
  });

  it("TIKLAMAYLA açılır ve önceki kart kapanır", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="genel" />);
    expect(screen.getByText("Genel gövde.")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Piyasa"));

    expect(screen.getByText("Piyasa gövdesi.")).toBeInTheDocument();
    expect(screen.queryByText("Genel gövde.")).not.toBeInTheDocument();
  });

  it("HOVER kartı AÇMAZ", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="genel" />);

    fireEvent.mouseEnter(screen.getByText("Piyasa"));

    expect(screen.queryByText("Piyasa gövdesi.")).not.toBeInTheDocument();
    expect(screen.getByText("Genel gövde.")).toBeInTheDocument();
  });

  it("degraded kart SEBEBİNİ söyler", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="risk" />);

    expect(screen.getByText(/özetlenemedi/)).toBeInTheDocument();
  });

  it("degraded olmayan kartta uyarı YOK", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="genel" />);

    expect(screen.queryByText(/özetlenemedi/)).not.toBeInTheDocument();
  });

  it("dört kartın başlığı da her zaman görünür", () => {
    render(<InsightCards cards={KARTLAR} initialCardId="genel" />);

    for (const kart of KARTLAR) {
      expect(screen.getByText(kart.title)).toBeInTheDocument();
    }
  });
});
