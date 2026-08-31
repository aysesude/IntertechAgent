> **Analiste gidecek not — 26 Ağustos 2026.** Uygulama sırasında `gerek.md` ve
> şartname tablosundan **bilerek** sapılan noktaların listesi. Her maddede
> sapmanın gerekçesi ve ölçüm dayanağı var. Onaylanan maddeler `gerek.md`'ye
> işlenmeli; reddedilenler kodda geri alınmalı.

# Kapsam sapmaları — analist onayı bekliyor

Yedi madde var. Dördü veri/kapsam kararı, ikisi **çelişki bildirimi**, biri
**ertelenmiş bir istek** (6. madde).

**Durum (2026-08-28):** 1, 2, 3, 3b ve 4 kararlaştı (Yağız); kod ve testler
buna göre güncellendi. 6 hâlâ ertelenmiş, 7 zaten karar gerektirmiyordu.

---

## 1. Mevduat varlık olarak kaldırıldı — ✅ KARARLAŞTI (2026-08-28)

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

**Karar (2026-08-28, analist onayı):** Mevduat kapsam dışı kalıyor. Faiz
işletme mekanizması eklenmeyecek, `MEVDUAT-V`/`MEVDUAT-VS` geri gelmeyecek.
Kod tarafında ek bir değişiklik gerekmiyor — mevcut hâl zaten bu kararla
uyumlu.

---

## 2. Uygunluk risk tablosu yeniden kalibre edildi — ✅ KARARLAŞTI (2026-08-28)

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

**Yeni tabloda yedi puanın yedisi de** farklı bir varlık kümesi açıyor, dört
profil dört farklı sonuç veriyor.

**7. seviye serbest fonla dolduruldu.** İlk tasarımda boş bırakılmıştı
("türev/kaldıraçlı ürün için ayrıldı") ama 700 TEFAS fonu tarandığında
kaldıraçlı, ters (inverse) ve girişim sermayesi fonu **sıfır** çıktı — yani o
tanımın TEFAS'ta karşılığı yok. Serbest fon (SPK III-52.1) boşluğu
dolduruyor: yalnızca **nitelikli yatırımcıya** satılır, portföy
sınırlamalarının çoğundan **muaftır**, izahnamesi **kaldıraç ve açığa satışa**
izin verir. `scope.yaml` "serbest fon"u zaten kapsam içi sayıyor.

Eklenen: **`BHE`** (Ak Portföy Birinci Hisse Senedi Serbest Fon), 256 gün
kesintisiz veri, %22,8 volatilite.

Elenen adaylar kayıt için: `GMI` (Gümüş Serbest) %61,4 ile en oynaktı ama
kaldıraçlı değil — **spot gümüş zaten %63,1**; `THV` %137 ölçtü ama üst üste
+%67/+%90 sıçraması var (veri kusuru); on istatistiksel arbitraj fonu
%2,1-4,7 — yapıca en karmaşık ürünler ama piyasa nötr.

**Karar (2026-08-28, Yağız):** Kademelerin yayılması onaylandı — eski tablo
artık kullanılmıyor. Gerekçe genişletildi: kullanıcının risk profili artık
anketten gelen bir puan olarak profilde duruyor (`users.risk_survey_score`);
tek tek varlıkların "ne kadar riskli" olduğunun ince ayarı bu sabit tabloda
DEĞİL, ilgili yerlerde LLM'in yorumuna bırakılıyor — bkz. madde 3 ve 4'teki
kararlar, ikisi de aynı ilkeyle bu tabloyu SADELEŞTİRME yönünde.

---

## 3. Kıymetli maden ↔ döviz sıralaması — `gerek.md` ile ÇELİŞKİ — ✅ KARARLAŞTI (2026-08-28)

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
| Gram altın | **%28,6** |
| Altın fonu (GTA) | **%25,6** |

TL'li yatırımcı için altın, dövizden **kat kat** oynak.

**Dikkat — dövizin düşük rakamı yanıltıcıdır:** USDTRY'nin standart sapmasının
küçük çıkması düşük risk değil, TL'nin düzenli değer kaybının yan ürünüdür
(seri neredeyse tek yönlü tırmandığı için sapma küçük ölçülür). Bu yüzden
dövizi en alta koymadık; TL tahvil fonlarının **üstünde** (3), madenin
**altında** tuttuk. `gerek.md`'nin "döviz tahvilden riskli" sezgisi bu yönüyle
korunuyor, yalnızca madenle olan sırası ters.

**Karar (2026-08-28, Yağız):** `gerek.md` esas alınır, kendi ölçümümüz
belirleyici değil ("bizim ölçümümüz önemli değil"). Döviz maden'in üstüne
çekildi: tabloda MADEN 3, DÖVİZ 4 (yer değiştirdi — kod: `backend/app/core/
config.py` → `ASSET_CLASS_ADVICE_RISK_LEVEL`).

### 3b. Gümüş ve platin madenden ayrıldı (4 → 5) — ✅ KARARLAŞTI (2026-08-28): AYRIM KALDIRILDI

Sınıf içi dağılım ölçüldüğünde kıymetli madenin tek kademeye sığmadığı
görüldü (365 gün, TL cinsinden):

| | ölçülen |
|---|---|
| Gram altın · sikkeler · altın fonu | %25,6 – %28,6 |
| **Gram platin** | **%55,3** |
| **Gram gümüş** | **%65,9** |

Gümüş ve platin, **yerli hissenin (%38,6, seviye 5) üstünde** oynuyor;
ondan düşük bir kademede duramazlar. İkisi varlık düzeyinde **5**'e çekildi,
gram altın ve sikkeler 4'te kaldı.

**Karar (2026-08-28, Yağız):** Kategori bütünlüğü — "ikisi de kıymetli
maden, ayırma". Gümüş/platin artık maden sınıfından (yeni seviyesi 3) ayrı
bir kademede değil; `AssetSpec.risk_level` override'ı kaldırıldı (kod:
`backend/app/providers/universe.py` → `_gram_metal` çağrıları).

---

## 4. Yabancı hisse yerlinin bir üstünde (6 / 5) — ✅ KARARLAŞTI (2026-08-28): AYRIM KALDIRILDI

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

**Karar (2026-08-28, Yağız):** Erişim temelli gerekçe reddedildi — "risk ile
alakalı değil". Yabancı hisse yerliyle aynı kademeye (5) çekildi;
`_foreign_stock`'taki `risk_level=6` ve `AFT`'teki aynı override kaldırıldı.
**Yan etki (bilinçli kabul edildi):** puan 5 ve puan 6 artık aynı varlık
kümesini açıyor — 6'yı 5'ten ayıran tek şey yabancı hisseydi. "Yedi puanın
yedisi de farklı sonuç verir" ölçütü altı farklı kümede tutuluyor artık
(bkz. `tests/test_advice_eligibility.py::test_her_puan_bir_oncekinden_
farkli_kume_acar`).

---

## 6. Bilerek uyumsuz demo kullanıcısı — ERTELENDİ

**İstenen:** seed'de 3-5 kullanıcı anket puanının izin vermediği varlık
tutsun ("profil düşürmüş" varsayımıyla), ki uyumsuzluk-uyarısı yolu demoda
görünsün.

**Yapılmadı.** İki gerekçe:

**(a) Ürün Sahibi bu kararı daha önce geri aldı.** `data/seed_ledger.py`
içinde kayıtlı (Not 5, 2026-08): önceki tasarım kasıtlı olarak uyumsuz
kombinasyonlar üretiyordu, PO bunu geri aldı — *"dummy veri artık
gerçekçi/tutarlı olmalı; uyumsuzluk-uyarısı yolu zaten kendi birim
testleriyle doğrulanıyor, dummy veride bunun için kasıtlı bir bozukluğa
gerek yok."*

**(b) Uyumsuzluk bugün hiçbir yerde deterministik olarak görünmüyor.** Tek
yol risk ajanının `profil_sapmasi` sinyali; o da LLM'in takdirine bağlı ve
`agents/risk_agent.py` **gerçek `risk_survey_score`'u değil, hâlâ geçici
dummy puanı** okuyor. Uyumsuz kullanıcı eklenseydi demoda güvenilir biçimde
hiçbir şey göstermezdi.

**Ön koşul:** gerçek anket puanının risk ajanına bağlanması ve uygunluk
ihlali için deterministik bir uyarı yolu. İkisi olduğunda bu madde yeniden
değerlendirilmeli.

**Bu arada uyum tarafı yapıldı:** seed portföyleri artık puana uyuyor,
ölçülen **31/50 → 0/50**.

---

## 7. Ölçek SRRI değil — adlandırma uyarısı

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

## Ek — iş kalemi (sapma değil, bilinen sınır): merge bazı web_research uyarılarını düşürebiliyor

**Not eklendi: 2026-08-28.** Bu madde bir kapsam sapması değil; analist onayı
beklemiyor, sadece iz bırakılıyor ki unutulmasın.

**Nereden çıktı:** `docs/AGENTS.md` → "Web Araştırma Ajanı" bölümünün kendi
"Bilinen sınır" notu (satır ~278-283). Ajanın metni kullanıcıya doğrudan
gitmiyor, `orchestrator.py`'nin `merge` adımında ikinci bir LLM turundan
geçiyor. `merge_responses`'ın "elenemez" listesinde (ALINAMAYAN BİLGİLER,
`Kaynaklar:`, canlı bloklar) web_research'ün **vergi konusu yönlendirmesi**
(`scope.yaml` → `kisitli_konular`'dan gelen mali müşavire yönlendirme) ve
**kapanış uyarısı** yok — yani merge bunları elemesi mümkün, ikinci LLM turu
bunları "gereksiz tekrar" sayıp düşürebiliyor.

**Neden hemen düzeltilmedi:** düzeltme `merge_responses`'ı değiştirmeyi
gerektiriyor; bu fonksiyon dört ajanı (portfolio/market/risk/web_research)
birden etkiliyor, tek bir ajanın notuyla izole edilecek bir değişiklik değil.
Bugünkü kalibrasyon/uygunluk işinden bağımsız, kendi başına bir iş.

**Durum:** yapılmadı, bekliyor. Kod: `agents/orchestrator.py` → `merge`
(→ `merge_responses`). Referans: `docs/AGENTS.md` "Web Araştırma Ajanı" →
"Bilinen sınır".

---

## Dayanaklar

Tüm volatilite değerleri 250 günlük gerçek fiyat serisinden ölçüldü
(yfinance / TEFAS / TCMB), 25-26 Ağustos 2026. Tablo ve gerekçeler kodda:
`backend/app/core/config.py` → `ASSET_CLASS_ADVICE_RISK_LEVEL`,
`backend/app/providers/universe.py` → `AssetSpec.risk_level`.
Ekip özeti: `docs/DATA.md` → "Uygunluk risk seviyesi (1-7)".
