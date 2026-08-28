"""Ajanların ortak Türkçe sayı biçimlendirmesi.

Portföy ve Piyasa ajanlarının ikisi de rakam basıyor; kopyalanmış iki
biçimlendirici er geç ayrışır ve aynı ekranda iki farklı para biçimi görünür.

Biçim kararları kasıtlı:

- Binlik ayıracı NOKTA, ondalık ayıracı VİRGÜL: 1.234,56
- Yüzde işareti sayıdan ÖNCE: %8,41 — Türkçe yazım kuralı böyle. Eskiden
  sonda basılıyordu ("8,41%") ve düzeltmeyi merge adımındaki LLM'e bırakmak
  gerekiyordu; model bunu çoğunlukla doğru yapıyor ama her zaman değil
  (ölçüldü: aynı yanıtta "%+8,21" gibi ters bir biçim çıktı). Kaynağında
  doğru üretmek, sonradan düzelttirmekten güvenli.
- İşaret en başta: +%8,41 / -%12,66
- Değer yoksa uzun tire: — (sıfır DEĞİL; "veri yok" ile "değer sıfır" ayrı
  şeyler, sıfır basmak uydurma olurdu).
"""

from typing import Any

# Varlık sınıfı → Türkçe ad. Portföy ve Piyasa ajanlarının ikisi de bir varlık
# sınıfını kullanıcıya göstermek zorunda kalıyor (2026-08-28); aynı gerekçeyle
# yukarıdaki sayı biçimlendiricileri burada: kopyalanmış iki çeviri sözlüğü er
# geç ayrışır (ör. biri günceller, diğeri unutulur) ve aynı sınıf iki ekranda
# farklı adla görünür.
ASSET_CLASS_TR = {
    "stock": "Hisse Senedi",
    "precious_metal": "Kıymetli Maden",
    "currency": "Döviz",
    # "Tahvil" DEĞİL: bu sınıfta doğrudan devlet tahvili yok, hepsi TEFAS
    # borçlanma araçları fonu. "Tahvil" demek olmayan bir enstrümanı ima
    # ediyordu; üstelik scope.yaml "tahvil"i kapsam dışı sayıyor.
    "bond": "Borçlanma Araçları",
    "cash": "Nakit",
}


def tr_amount(value: Any, *, signed: bool = False) -> str:
    """1234.5 -> '1.234,50'. `signed` ise işaret hep yazılır."""
    if value is None:
        return "—"
    text = f"{float(value):+,.2f}" if signed else f"{float(value):,.2f}"
    # Ayıraçları takas et: önce virgülleri bir yer tutucuya al, yoksa
    # noktaları virgüle çevirirken kendi ürettiğimiz virgülleri de bozarız.
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def tr_percent(value: Any, *, signed: bool = False) -> str:
    """8.41 -> '%8,41'; `signed` ile '+%8,41'."""
    if value is None:
        return "—"
    sayi = f"{abs(float(value)):.2f}".replace(".", ",")
    if not signed:
        return f"%{sayi}"
    isaret = "+" if float(value) >= 0 else "-"
    return f"{isaret}%{sayi}"


def tr_date(value: Any) -> str:
    """ISO tarihini GG.AA.YYYY biçimine çevirir: '2025-09-08T10:00:00Z' -> '08.09.2025'.

    Ayrıştırılamayan değer olduğu gibi bırakılır, tarih uydurulmaz; değer yoksa
    uzun tire (yukarıdaki biçim kararlarıyla aynı).
    """
    if value is None:
        return "—"
    text = str(value)[:10]
    parts = text.split("-")
    if len(parts) != 3:
        return text or "—"
    year, month, day = parts
    return f"{day}.{month}.{year}"
