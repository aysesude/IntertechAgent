import type { ChatMessage } from "@/types/finance";

/**
 * Sohbet dökümü — GEÇİCİ test aracı.
 *
 * Amacı: ajanların/RAG'ın verdiği yanıtları elle kopyalamadan toplayıp
 * inceleyebilmek. Soru-yanıt sırası, hangi ajanın cevapladığı ve yarım
 * kalan/hatalı yanıtlar korunur — bir yanıtın neden bozuk olduğunu sonradan
 * anlamak için hepsi gerekiyor.
 *
 * Sunum sonrası kaldırılacak; kullanıcıya dönük kalıcı bir özellik değil.
 */

const AYIRAC = "=".repeat(72);

function zamanDamgasi(): string {
  const simdi = new Date();
  const tarih = simdi.toLocaleDateString("tr-TR");
  const saat = simdi.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  return `${tarih} ${saat}`;
}

/** Dosya adında iki nokta ve boşluk sorun çıkarır. */
function dosyaAdi(): string {
  const simdi = new Date();
  const iki = (n: number) => String(n).padStart(2, "0");
  return (
    `vira-sohbet-${simdi.getFullYear()}${iki(simdi.getMonth() + 1)}${iki(simdi.getDate())}` +
    `-${iki(simdi.getHours())}${iki(simdi.getMinutes())}.txt`
  );
}

export function buildTranscript(messages: ChatMessage[], kullanici: string): string {
  const sorular = messages.filter((m) => m.role === "user").length;
  const yanitlar = messages.filter((m) => m.role === "assistant").length;

  const baslik = [
    "VİRA — Sohbet Dökümü",
    `Oluşturulma : ${zamanDamgasi()}`,
    `Kullanıcı   : ${kullanici || "—"}`,
    `Mesaj       : ${sorular} soru, ${yanitlar} yanıt`,
    "",
    AYIRAC,
  ];

  const govde: string[] = [];
  let sira = 0;

  for (const mesaj of messages) {
    if (mesaj.role === "user") {
      sira += 1;
      govde.push("", `[${sira}] SORU · ${mesaj.createdAt}`, "", mesaj.text, "");
      continue;
    }

    // Ajan adı yalnızca `done` olayıyla geliyor; hata durumunda hiç gelmiyor.
    const etiketler = [`YANIT · ${mesaj.createdAt}`];
    if (mesaj.agentName) etiketler.push(mesaj.agentName);
    govde.push(`--- ${etiketler.join(" · ")} ---`, "");
    govde.push(mesaj.text.trim() ? mesaj.text : "(boş yanıt)");

    // Bu iki satır dökümün asıl işini görüyor: bozuk yanıtın NEDEN bozuk
    // olduğu, metnin kendisinden okunamıyor.
    if (mesaj.error) govde.push("", `[HATA] ${mesaj.error}`);
    if (mesaj.incomplete) govde.push("", "[EKSİK] Akış tamamlanmadan koptu.");

    govde.push("", AYIRAC);
  }

  if (sira === 0) govde.push("", "(Bu oturumda hiç mesaj yok.)", "");

  return [...baslik, ...govde, ""].join("\n");
}

/** Dökümü .txt olarak indirir. */
export function downloadTranscript(messages: ChatMessage[], kullanici: string): void {
  // BOM: Windows'ta Not Defteri BOM'suz UTF-8'i sistem kod sayfası sanıp
  // Türkçe karakterleri bozuyor. Dökümün ilk okuyucusu orası olacak.
  const blob = new Blob(["﻿" + buildTranscript(messages, kullanici)], {
    type: "text/plain;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const baglanti = document.createElement("a");
  baglanti.href = url;
  baglanti.download = dosyaAdi();
  document.body.appendChild(baglanti);
  baglanti.click();
  document.body.removeChild(baglanti);
  // Sekme kapanana kadar blob bellekte kalırdı.
  URL.revokeObjectURL(url);
}
