/**
 * T.C. kimlik numarası doğrulaması.
 *
 * Sunucu bu sağlamayı BİLEREK yapmıyor (bkz. backend/app/schemas/auth.py):
 * geçersiz bir numara zaten hiçbir kayıtla eşleşmez ve ayrı bir hata mesajı
 * üretmek "bu numara sistemde kayıtlı mı" sorusuna dolaylı cevap verirdi.
 *
 * İstemcide ise anlamlı: kullanıcı yanlış yazdığında ağa çıkmadan, anında
 * "numara geçersiz" diyebiliyoruz. Bu bir güvenlik kapısı değil, yazım
 * hatasını erken yakalayan bir kolaylık.
 *
 * Algoritma:
 * - 11 hane, tamamı rakam, ilk hane 0 olamaz
 * - 10. hane: (tek sıradakilerin toplamı × 7 − çift sıradakilerin toplamı) mod 10
 * - 11. hane: ilk on hanenin toplamı mod 10
 */
export function gecerliTcKimlikNo(numara: string): boolean {
  if (numara.length !== 11 || !/^\d{11}$/.test(numara) || numara[0] === "0") {
    return false;
  }
  const hane = [...numara].map(Number);
  const tekler = hane[0] + hane[2] + hane[4] + hane[6] + hane[8];
  const ciftler = hane[1] + hane[3] + hane[5] + hane[7];
  const onuncu = (tekler * 7 - ciftler) % 10;
  const onbirinci = hane.slice(0, 10).reduce((t, h) => t + h, 0) % 10;
  return hane[9] === onuncu && hane[10] === onbirinci;
}
