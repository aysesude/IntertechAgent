> **Analiste gidecek not — 26 Ağustos 2026.** Uygulama sırasında `gerek.md` ve
> şartname tablosundan **bilerek** sapılan noktaların listesi. Her maddede
> sapmanın gerekçesi ve ölçüm dayanağı var. Onaylanan maddeler `gerek.md`'ye
> işlenmeli; reddedilenler kodda geri alınmalı.

# Kapsam sapmaları — analist onayı bekliyor

Beş madde var. Üçü veri/kapsam kararı, ikisi bir **çelişki bildirimi**.

---

## 1. Mevduat varlık olarak kaldırıldı

**Ne yapıldı:** `MEVDUAT-V` (vadeli) ve `MEVDUAT-VS` (vadesiz) varlıkları
evrenden çıkarıldı. `AssetClass.CASH` altında artık **hiç varlık yok**; nakit
yalnızca defterdeki serbest bakiyedir.

**`gerek.md` §2 ne diyor:** varlık sınıfları arasında "Nakit (Vadeli, Vadesiz
mevduat)" sayılıyor. **Bu bir sapmadır.**

**Gerekçe:** `agents/scope.yaml` mevduatı zaten **iki ayrı listede** kapsam
dışı sayıyor (`sabit_getirili` ve `bankacilik_urunleri`). Yani sohbet "vadeli
mevduat nedir" sorusunu "kapsam dışı" diye reddederken portföy mevduat
tutuyordu. Ayrıca sistemde **faiz işletme mekanizması yok**: birim fiyatı
sabit 1 TL olan bu iki kayıt, getirisi `INTEREST` işlemiyle elle yazılmadıkça
düz çizgi kalıyordu ve çekilecek gerçek bir piyasa fiyatları yoktu — evrendeki
**son sentetik varlıklar** onlardı.

**Yan etkisi:** `TransactionType.INTEREST` demoda yalnızca mevduat faizinden
üretiliyordu; **artık hiç üretilmiyor.** Tip şemada duruyor, veri yok.

**Kazanç:** evren tamamen gerçek kaynaklı hâle geldi (**AK 5.1**).

**Karar gerekiyor:** mevduat kapsam dışı mı, yoksa faiz mekanizmasıyla
birlikte geri mi gelmeli?

---

## 2. Uygunluk risk tablosu yeniden kalibre edildi

**Şartnamedeki tablo** (koda birebir alınmıştı):

| | NAKIT | TAHVIL | DOVIZ | ALTIN | HISSE |
|---|---|---|---|---|---|
| eski | 1 | 3 | 4 | 4 | 6 |
| **yeni** | 1 | **2** | **3** | 4 | **5** |

**Sorun (ölçüldü):** eski tablo yedi puandan yalnızca **dört farklı sonuç**
üretiyordu:

```
1 -> nakit            2 -> nakit           (2, 1 ile aynı)
3 -> +tahvil          4 -> +döviz, altın
5 -> (4 ile aynı)     6 -> +hisse          7 -> (6 ile aynı)
```

Yani anket 1-7 arası puan verirken sistemin ayırt edebildiği kademe sayısı
dörttü; 2, 5 ve 7 puanları kullanıcı için hiçbir şeyi değiştirmiyordu. Aynı
kusur risk ajanının profil eşlemesine de yansımıştı: **DENGELİ ve BÜYÜME
profilleri birebir aynı izin kümesini** alıyordu.

Ayrıca eski tabloda muhafazakâr kullanıcıya (puan 2) önerilebilecek **tek şey
nakitti** — nakit sınıfında satın alınabilir varlık olmadığı için pratikte
hiçbir şey.

**Yeni tabloda** 1-6 arası her puan farklı bir varlık kümesi açıyor
(**6 farklı sonuç**), dört profil dört farklı sonuç veriyor. **7 bilerek boş
bırakıldı**, türev/kaldıraçlı ürünler için ayrıldı — tepede yer kalsın ki yeni
bir ürün geldiğinde tüm tabloyu kaydırmak gerekmesin.

**Karar gerekiyor:** kademelerin yayılması onaylanıyor mu?

---

## 3. Kıymetli maden ↔ döviz sıralaması — `gerek.md` ile ÇELİŞKİ

**`gerek.md` §2:** Kıymetli maden → *"Orta"*, Döviz → *"Orta-Yüksek"*.
Yani **döviz madenin üstünde** olmalı.

**Şartname tablosu:** ikisi de **4** (eşit).

**Bizim tablomuz:** döviz **3**, maden **4** — yani **maden dövizin üstünde**,
`gerek.md`'nin tam tersi.

Üç kaynak üç farklı şey söylüyor; biri seçilmeli.

**Ölçüm bizim sıralamamızı destekliyor** (yıllık volatilite, TL cinsinden):

| | ölçülen |
|---|---|
| USDTRY | ~%1 |
| EURTRY / GBPTRY / CHFTRY | %0,9 – %7,1 |
| Gram altın | **%24** |
| Altın fonu (GTA) | **%25,6** |

TL'li yatırımcı için altın, dövizden **kat kat** oynak.

**Dikkat — dövizin düşük rakamı yanıltıcıdır:** USDTRY'nin standart sapmasının
küçük çıkması düşük risk değil, TL'nin düzenli değer kaybının yan ürünüdür
(seri neredeyse tek yönlü tırmandığı için sapma küçük ölçülür). Bu yüzden
dövizi en alta koymadık; TL tahvil fonlarının **üstünde** (3), madenin
**altında** tuttuk. `gerek.md`'nin "döviz tahvilden riskli" sezgisi bu yönüyle
korunuyor, yalnızca madenle olan sırası ters.

**Karar gerekiyor:** hangisi geçerli — `gerek.md` mi, ölçüm mü?

---

## 4. Yabancı hisse yerlinin bir üstünde (6 / 5)

Evrene **21 ABD hissesi** eklendi (`scope.yaml` NASDAQ / S&P 500 / Dow
Jones'u zaten kapsam içi sayıyordu ama evrende hiç yoktu).

**Uygunlukta yabancı hisse 6, yerli hisse 5.**

**Gerekçe volatilite DEĞİL — ölçüm tersini söylüyor:**

| | ölçülen ortalama |
|---|---|
| ABD hisseleri (21) | **%28,8** |
| BIST hisseleri | **%38,6** |

Gerekçe **erişim ve karmaşıklık**: kur maruziyeti, sınır ötesi saklama, yerel
yatırımcı korumasının bulunmaması, farklı vergi rejimi. Kodda ve
`docs/DATA.md`'de böyle yazıldı; "daha oynak" denseydi rakamlara bakan ilk
kişi yakalardı.

**Karar gerekiyor:** erişim temelli bu gerekçe kabul mü, yoksa yabancı hisse
yerliyle aynı kademeye mi (5) çekilsin?

---

## 5. Ölçek SRRI değil — adlandırma uyarısı

Sistemde **iki ayrı 1-7 ölçeği** var ve karıştırılmaya çok müsait:

| | Nereden çıkar | Nerede |
|---|---|---|
| `RiskLevel` | Portföyün **ölçülen volatilitesinden** (SRRI bantları) | `risk_service` |
| Uygunluk seviyesi | **Ürün kategorisinden** (elle tablo) | `advice_eligibility` |

İkisi aynı şey değildir ve birbirine dönüştürülemez. Örnek: AK2 (uzun vadeli
TL borçlanma fonu) SRRI'de **5** çıkıyor (%10 volatilite) ama uygunlukta
**2**'dir — çünkü uygunluk "hangi ürün hangi yatırımcıya sunulabilir"
sorusunun cevabıdır, oynaklık ölçüsü değil.

**Karar gerekmiyor**, ama analiz dokümanında bu ayrımın adlandırmayla
belirginleştirilmesi öneriliyor (ör. "uygunluk seviyesi" / "risk seviyesi").

---

## Dayanaklar

Tüm volatilite değerleri 250 günlük gerçek fiyat serisinden ölçüldü
(yfinance / TEFAS / TCMB), 25-26 Ağustos 2026. Tablo ve gerekçeler kodda:
`backend/app/core/config.py` → `ASSET_CLASS_ADVICE_RISK_LEVEL`,
`backend/app/providers/universe.py` → `AssetSpec.risk_level`.
Ekip özeti: `docs/DATA.md` → "Uygunluk risk seviyesi (1-7)".
