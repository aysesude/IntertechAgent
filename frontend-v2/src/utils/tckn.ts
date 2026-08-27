/**
 * T.C. kimlik numarası biçim kontrolü.
 *
 * YALNIZCA BİÇİM: 11 hane, tamamı rakam. Sağlama (checksum) doğrulaması
 * BİLEREK KALDIRILDI.
 *
 * Neden: bu bir demo ve kullanıcı verisi sentetik. Sağlama kontrolü,
 * hesap açmak isteyen bir denemeciyi gerçek bir T.C. kimlik numarası
 * girmeye zorluyordu — sunumda kimseden kendi kimlik numarasını istemek
 * doğru değil, uydurulan numaralar da sağlamadan geçmiyordu. Kayıt akışı
 * bu yüzden pratikte kullanılamaz hâldeydi.
 *
 * Sunucu zaten aynı kuralı uyguluyor (11 hane + rakam, bkz.
 * backend/app/schemas/auth.py); sağlamayı orada da hiç yapmıyoruz çünkü
 * geçersiz bir numara zaten hiçbir kayıtla eşleşmez ve ayrı bir hata
 * mesajı üretmek "bu numara sistemde kayıtlı mı" sorusuna dolaylı cevap
 * verirdi.
 *
 * Bu bir güvenlik kapısı değil, yazım hatasını ağa çıkmadan yakalayan bir
 * kolaylık.
 */
export function gecerliTcKimlikNo(numara: string): boolean {
  return /^\d{11}$/.test(numara);
}
