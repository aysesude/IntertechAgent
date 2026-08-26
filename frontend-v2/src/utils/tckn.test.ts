import { describe, expect, it } from "vitest";
import { gecerliTcKimlikNo } from "./tckn";

/**
 * Beklenen değerler seed'in ÜRETTİĞİ gerçek numaralardan alındı
 * (`make demo-users` çıktısı) — uydurma örneklerle test etmek algoritmanın
 * gerçek veriyle uyumlu olduğunu göstermez.
 */
describe("gecerliTcKimlikNo", () => {
  it.each(["55868501480", "89911838490", "36542351188", "20433218148"])(
    "seed'in ürettiği %s geçerli sayılır",
    (numara) => {
      expect(gecerliTcKimlikNo(numara)).toBe(true);
    },
  );

  it.each([
    ["", "boş"],
    ["1234567890", "10 hane"],
    ["123456789012", "12 hane"],
    ["0123456789A", "harf içeriyor"],
    ["01234567890", "sıfırla başlıyor"],
    ["55868501481", "son hane bozuk"],
    ["55868501490", "onuncu hane bozuk"],
    ["11111111111", "sağlama tutmuyor"],
  ])("%s reddedilir (%s)", (numara) => {
    expect(gecerliTcKimlikNo(numara)).toBe(false);
  });
});
