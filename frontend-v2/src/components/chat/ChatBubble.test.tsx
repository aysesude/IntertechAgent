import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "@/types/finance";
import { ChatBubble } from "./ChatBubble";

/**
 * Balonun görsel sözleşmesi.
 *
 * Buradaki iki değişmez de gözle yakalanması kolay ama koda geri sızması da
 * kolay şeyler; ikisi de bir kez bozulmuştu.
 */

beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function mesaj(ustuneYaz: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "m1",
    role: "assistant",
    text: "Merhaba",
    createdAt: "10:00",
    ...ustuneYaz,
  };
}

/** Balonun kendisi: metni taşıyan, yuvarlatılmış kutu. */
function balon(): HTMLElement {
  const el = document.querySelector<HTMLElement>('[class*="rounded-[14px]"]');
  if (!el) throw new Error("balon bulunamadı");
  return el;
}

describe("ChatBubble", () => {
  it("kullanıcı ve asistan balonları FARKLI zeminde", () => {
    // İkisi de `bg-brand` idi; kimin konuştuğu yalnızca hizadan
    // anlaşılıyordu. Asistan tarafı nötr, çünkü uzun olan taraf o —
    // markdown listeleri ve rakamlar doygun zeminde yorucu okunuyor.
    const { unmount } = render(<ChatBubble message={mesaj({ role: "assistant" })} />);
    const asistan = balon().className;
    unmount();

    render(<ChatBubble message={mesaj({ role: "user", text: "Selam" })} />);
    const kullanici = balon().className;

    expect(asistan).toContain("bg-line2");
    expect(kullanici).toContain("bg-brand");
    expect(asistan).not.toContain("bg-brand");
  });

  it("genişlik sınırı balonda DEĞİL, sarmalayıcıda", () => {
    // `max-w-[84%]` balonun üstündeyken yüzde, içeriğe göre belirlenen bir
    // kutuya karşı çözülüyordu: tarayıcı doğal metin genişliğinin %84'ünü
    // uyguluyor, bol yer varken kısa mesajlar bile ikinci satıra düşüyordu.
    render(<ChatBubble message={mesaj({ role: "user", text: "Selam" })} />);

    const kutu = balon();
    expect(kutu.className).not.toMatch(/max-w-/);
    // Sarmalayıcı satırın tam genişliğinde, yüzde orada beklendiği gibi
    // çözülüyor.
    expect(kutu.parentElement?.className).toMatch(/max-w-\[90%\]/);
  });

  it("akış sürerken bekleme işareti balonun İÇİNDE", () => {
    render(<ChatBubble message={mesaj({ text: "", streaming: true })} />);

    // Etiket `white-space: nowrap`; balon dar kalırsa taşıyordu. Genişlik
    // düzeltmesinden sonra balon işarete göre büyüyor.
    expect(screen.getByText("VİRA düşünüyor")).toBeInTheDocument();
    expect(balon()).toContainElement(screen.getByText("VİRA düşünüyor"));
  });

  it("hata balonu kendi biçiminde kalır", () => {
    render(<ChatBubble message={mesaj({ error: "Bağlantı koptu" })} />);
    expect(balon().className).toContain("bg-danger-tint");
  });
});
