import { describe, expect, it } from "vitest";
import { gecerliTcKimlikNo } from "./tckn";

/**
 * Kontrol YALNIZCA BİÇİM: 11 hane, tamamı rakam.
 *
 * Sağlama (checksum) doğrulaması bilerek kaldırıldı — gerekçesi `tckn.ts`
 * başlığında. Bu dosya o kararı kilitliyor: sağlaması tutmayan ama biçimi
 * doğru bir numara ARTIK KABUL EDİLMELİ, aksi hâlde kayıt akışı denemeciyi
 * gerçek bir kimlik numarası girmeye zorlar.
 */
describe("gecerliTcKimlikNo", () => {
  it.each(["55868501480", "89911838490", "36542351188", "20433218148"])(
    "seed'in ürettiği %s geçerli sayılır",
    (numara) => {
      expect(gecerliTcKimlikNo(numara)).toBe(true);
    },
  );

  it.each([
    ["11111111111", "sağlaması tutmuyor ama biçimi doğru"],
    ["01234567890", "sıfırla başlıyor"],
    ["55868501481", "eski sağlamaya göre son hanesi bozuk"],
    ["12345678901", "sıradan bir deneme numarası"],
  ])("%s kabul edilir (%s)", (numara) => {
    expect(gecerliTcKimlikNo(numara)).toBe(true);
  });

  it.each([
    ["", "boş"],
    ["1234567890", "10 hane"],
    ["123456789012", "12 hane"],
    ["0123456789A", "harf içeriyor"],
    ["1234567890 ", "boşluk içeriyor"],
  ])("%s reddedilir (%s)", (numara) => {
    expect(gecerliTcKimlikNo(numara)).toBe(false);
  });
});
