# Doküman Klasörü — Toplama Kılavuzu

Bu klasördeki dosyalar RAG pipeline'ı tarafından okunup vektör veritabanına
yüklenecek. Piyasa Araştırma Ajanı sorulara bu dokümanlara dayanarak cevap
verecek.

**Hedef: 30-50 doküman.** Az olursa ajan "bilmiyorum" der, çok olursa
toplama işi demoyu geciktirir.

---

## Dosya formatı

Her doküman bir `.md` dosyası. Dosyanın başında **front matter** denen bir
bilgi bloğu var — RAG bunu okuyup filtreleme yapıyor.

```markdown
---
baslik: ASELSAN 2026 2. Çeyrek Finansal Sonuçları
kaynak: KAP
kaynak_url: https://www.kap.org.tr/tr/Bildirim/1234567
tarih: 2026-07-28
sirket: ASELS
tur: bilanco
donem: 2026-Q2
konsolide_mi: true
dil: tr
---

Buradan itibaren dokümanın metni başlıyor.

Paragraflar normal markdown olarak yazılır. Başlıklar, listeler ve
tablolar kullanılabilir.
```

### Alanların anlamı

| Alan | Zorunlu | Açıklama |
|---|---|---|
| `baslik` | Evet | Dokümanın adı, cevaplarda kaynak olarak gösterilecek |
| `kaynak` | Evet | KAP, Bloomberg HT, Banka Araştırma, vb. |
| `kaynak_url` | Hayır | Varsa orijinal bağlantı |
| `tarih` | Evet | `YYYY-AA-GG` formatında. Ajan "son çeyrek" gibi soruları buna göre filtreler |
| `sirket` | Hayır | Borsa kodu (`ASELS`, `THYAO`). Genel piyasa haberlerinde boş bırakılır |
| `tur` | Evet | `haber` · `bilanco` · `analiz` · `duyuru` · `makro` |
| `donem` | `tur: bilanco` ise Evet | `YYYY-Qn` formatında (ör. `2026-Q2`). Hangi çeyreğe ait olduğunu deterministik filtreler için işaretler — eksikse "yanlış çeyrek döndürme" riskine karşı korunamaz |
| `konsolide_mi` | `tur: bilanco` ise Evet | `true`/`false`. Solo ile konsolide tablo aynı çeyrekte farklı rakamlar verir; hangisi olduğu belirsizse karıştırılabilir |
| `dil` | Evet | `tr` veya `en` |

---

## Dosya adlandırma

```
YYYY-AA-GG_SIRKET_kisa-aciklama.md
```

Örnekler:

```
2026-07-28_ASELS_ceyrek-sonuclari.md
2026-08-03_THYAO_yolcu-trafigi-duyurusu.md
2026-08-05_MAKRO_tcmb-faiz-karari.md
```

Şirkete özel değilse `SIRKET` yerine `MAKRO` veya `PIYASA` yaz.

---

## İçerik kuralları

**Uzunluk:** 300-2000 kelime arası ideal. Çok kısa dokümanlar anlamlı bağlam
taşımıyor, çok uzunlar parçalara bölünürken bağlamı kaybediyor.

**Sayılar önemli.** "Kâr arttı" yerine "net kâr 2,4 milyar TL'ye yükseldi
(geçen yıl 1,8 milyar TL)" yaz. Ajan sayısal karşılaştırma yapabilsin.

**Tabloları koru.** Markdown tablosu olarak bırak, düz metne çevirme.

**Telif.** Haber metinlerini olduğu gibi kopyalamak yerine özetleyerek yaz,
kaynağı `kaynak_url` alanında belirt. Bu hem telif riskini azaltır hem de
dokümanı daha odaklı hale getirir.

**Çeşitlilik.** Hepsi aynı şirket ya da aynı tür olmasın. Demo sırasında
farklı sorular sorulacak; dağılım şöyle olsun:

- ~15 şirket bilançosu / finansal sonuç
- ~15 piyasa haberi
- ~10 analist yorumu
- ~10 makroekonomik gelişme (faiz, enflasyon, kur)

---

## Nereden toplanır

**KAP (Kamuyu Aydınlatma Platformu)** — şirket bildirimleri, finansal
tablolar. Halka açık ve kullanımı serbest.

**Şirketlerin yatırımcı ilişkileri sayfaları** — faaliyet raporları,
sunumlar.

**TCMB** — faiz kararları, enflasyon raporları.

**Finansal haber siteleri** — özetleyerek, kaynak belirterek.

---

## Ekledikten sonra

Dosyalar git'e commit edilir (metin dosyaları küçük, sorun olmaz):

```bash
git checkout test && git pull
git checkout -b feature/dokuman-ekleme
git add data/documents/
git commit -m "RAG icin 12 finansal dokuman eklendi"
git push -u origin feature/dokuman-ekleme
```

Sonra `test`'e PR aç. Merge edilince sunucuya otomatik gider.

Merge sonrası (veya kendi lokalinde) dokümanlar şu komutla vektör
veritabanına işlenir — tekrar çalıştırmak güvenlidir, kopya yaratmaz:

```bash
docker compose exec -w / api python -m rag.ingest
```

---

## Örnek

Bu klasördeki gerçek dokümanlardan birine bak (ör. bir `bilanco`
dosyasını) — kopyalayıp üzerine yazabilirsin.

**Sahte/şablon içerik bu klasöre eklenmemeli.** Daha önce burada bir
`ornek-dokuman.md` şablonu vardı; gerçek dokümanlarla neredeyse aynı
kalıpta yazıldığı için (aynı başlıklar, aynı üslup) RAG sorgularında
gerçek şirket verisiyle karışıyordu — ölçümle doğrulandı, kaldırıldı.
Format örneği için artık gerçek bir doküman kopyalanmalı.
