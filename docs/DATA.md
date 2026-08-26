# Veri Katmanı El Kitabı

> Hedef kitle: bu projeye ilk gün katılan geliştirici. Bu sayfayı okuduktan
> sonra veri katmanını kullanmak için kimseye soru sormanız gerekmemeli.
> Tasarım gerekçeleri için kök dizindeki `DB-PLANI.md` + `VERI-KATMANI-PLANI.md`.

## 1. Tek cümlelik model

**`transactions` yazılan gerçektir (append-only defter); `holdings` ondan
türetilen önbellektir; `price_history` dış dünyadır. Üçü birbirine karışmaz.**

```
providers/  (TCMB, yfinance, TEFAS, İş Portföy)      kullanıcı işlemleri
        │                                                   │
        ▼                                                   ▼
services/price_ingest.py  ──► price_history      ledger_service.record_transaction
   (kaynak öncelikli upsert)      │                  ──► transactions (append-only)
                                  │                         │
                                  │                         ▼
                                  │              ledger_service.rebuild_holdings
                                  │                  ──► holdings (önbellek)
                                  ▼                         │
                        valuation_service  ◄────────────────┘
                 (değer serisi, TWR, K/Z, kur dönüşümü)
```

## 2. Altın kurallar (ihlal = kırmızı test)

1. **Deftere yalnızca `ledger_service.record_transaction` yazar.** UPDATE ve
   DELETE yok; düzeltme ters kayıtla yapılır.
2. **`holdings`'i yalnızca `rebuild_holdings` yazar.** Elle holdings yazan kod
   `test_ledger_reconciliation`'ı kırar.
3. **`price_history`'ye yalnızca `price_ingest.upsert_prices` yazar.** Upsert
   önceliği: `synthetic(0) < derived(1) < yfinance(2) < tefas/isportfoy(3) <
   tcmb(4)`. Gerçek veri sentetiği ezer; sentetik gerçeği **asla** ezemez.
3b. **Sentetik satır gerçek serinin içine karışamaz.** Öncelik kuralı yalnızca
   AYNI güne iki kayıt geldiğinde çalışır; gerçek kaynağın hiç yayın yapmadığı
   günde (resmî tatil — `trading_days()` tatilleri bilmez) sentetik satır
   üzerine yazılmadan kalır. `seed_prices_synthetic` sonunda
   `drop_synthetic_where_real_exists` bunları siler: gerçek kapsaması
   `MIN_REAL_ROWS_FOR_PURE_REAL`'i aşan varlıkta sentetik hiç kalmaz, altında
   kalan varlıkta yalnızca gerçek aralığın içindeki delikler temizlenir.
   Tatilde fiyatın hiç olmaması doğrudur — piyasa kapalıydı.
4. **Fiyat/para her zaman `Decimal`**; float yasak.
5. **Sağlayıcılar (providers/) saftır:** DB'ye dokunmaz, `except: pass` yapmaz,
   hata durumunda `ProviderError` fırlatır.
6. **Kod İngilizce, kullanıcıya dönen metin Türkçe.** Kaynak/kimlik bilgisi
   yalnızca `.env`'de (CI'da gitleaks taraması var).

## 3. İşaret sözleşmesi (transactions)

- `quantity` her zaman ≥ 0; yön `transaction_type`'tan okunur.
- `cash_amount_try` işaretlidir: **BUY/WITHDRAW/FEE → negatif**,
  **SELL/DEPOSIT/DIVIDEND/INTEREST → pozitif**.
- Nakit bakiyesi = `SUM(cash_amount_try)`; hiçbir anda negatif olamaz
  (`record_transaction` kontrol eder).
- `fx_rate_to_try` işlem anındaki kurdur ve dondurulur; `avg_cost_price` TRY
  cinsinden, komisyon dahil birim maliyettir.
- DEPOSIT/WITHDRAW/INTEREST/FEE varlığa bağlanmaz (`asset_id NULL`);
  BUY/SELL/DIVIDEND varlık ister (CHECK ile zorlanır).

## 4. Nasıl yapılır?

### Lokal kurulum
```bash
cp .env.example .env       # gerekirse EVDS_API_KEY doldurun
docker compose up -d postgres
docker compose exec api alembic upgrade head
make seed                  # 50 kullanıcı + sentetik fiyat + işlem defteri
```
Docker yoksa: `.venv` ile `alembic upgrade head && python -m data.generate_dummy`
(pytest `PYTHONPATH=. backend` ile SQLite üzerinde koşar: `pytest -q`).

### Gerçek fiyat verisi çekmek
```bash
make backfill              # bir kerelik: 365 günlük gerçek geçmiş
make daily-update          # her gün: günün fiyatları (test sunucusunda cron'da)
make seed                  # ZORUNLU son adım — aşağıya bakın
```

**Backfill'den sonra `make seed` çalıştırılmalı.** İki sebeple:

1. Gerçek veri tatil günlerinde boşluk bırakır; temizlik
   (`drop_synthetic_where_real_exists`) seed içinde koşar (altın kural 3b).
2. `seed_ledger` işlem fiyatlarını `price_history`'den okur. Backfill sentetik
   fiyatları gerçekle değiştirdiğinde eski defter, artık var olmayan
   fiyatlardan alınmış görünür: maliyet bir evrenden, değerleme başka
   evrenden gelir. Ölçülen sonuç 20 Ağustos 2026'da 151 işlem / 48 portföyde
   sahte kâr-zarardı (bir varlıkta +%292).

**Yeni varlık eklediyseniz ekstra bir şey yapmanıza gerek YOK.** `backfill` ve
`daily-update` çalışmaya başlamadan önce varlık kataloğunu kendileri hizalıyor
(`seed_assets`). Bir süre öyle değildi: fiyat yazmak için varlığın DB kaydı
gerekiyor ve kayıt yoksa sembol sessizce atlanıyordu ("varlık DB'de yok"),
dolayısıyla yeni varlıkta sıra `seed → backfill → seed` olmak zorundaydı —
yani prosedür varlığın yaşına göre değişiyordu. Artık her durumda aynı.

Sonuçlar `data_ingest_log`'a yazılır. Başarısız kaynak DB'deki son veriyi
bozmaz; `make seed` de birikmiş gerçek veriyi silemez (öncelik kuralı).

### Sunucuda çalışırken iki tuzak

**`docker compose restart` `.env`'i YENİDEN OKUMAZ.** Konteyneri mevcut
ortamıyla yeniden başlatır. Ayar değiştirdiyseniz `up -d` gerekiyor
(konteyneri yeniden yaratır). Bir kez tam bu yüzden `ANCHOR_DATE`
değişikliği geçmedi ve seed eski ankrajla koştu.

**`0 satır` başarısızlık değildir.** `rows_upserted` YAZILAN satır sayısıdır,
çekilen değil. Geçmişi zaten tam olan bir sembol `0` yazar ve bu doğrudur;
işarete bakın: `+` başarılı, `-` atlandı, `!` başarısız, `~` kısmi.

### Varlık evreni (141 varlık)

| Sınıf | Adet | Kaynak |
|---|---|---|
| Hisse | 124 | yfinance (BIST 100'den 98 hisse + endeks + **21 ABD hissesi**) + TEFAS (3 hisse fonu + 1 serbest fon) |
| Kıymetli maden | 8 | yfinance (3 gram) + türetilmiş (4 sikke) + TEFAS (altın fonu) |
| Döviz | 4 | TCMB EVDS / today.xml, yedek yfinance |
| Borçlanma Araçları | 5 | TEFAS (4 borçlanma fonu + 1 para piyasası fonu) |
| Nakit | **0** | varlık yok — serbest bakiye (aşağıya bakın) |

**Evrende sentetik varlık YOK.** Tamamı gerçek kaynaklı (AK 5.1).
`test_no_asset_is_synthetic` bunu kilitliyor.

### Nakit bir varlık DEĞİL
`AssetClass.CASH` altında hiçbir varlık yoktur ve olmamalıdır
(`test_cash_class_has_no_assets`). Nakit, defterdeki **serbest bakiyedir**:
alım/satım için elde duran para. `portfolio_service` onu
`ledger_service.cash_balance_as_of` ile okuyup toplam değere ve nakit
dilimine ekler; temsil etmek için bir varlığa gerek yoktur.

Eskiden o dilim ÜÇ ayrı şeyi topluyordu — serbest bakiye, iki mevduat
varlığı ve bir "para piyasası fonu" — ve portföyleri olduğundan likit ve
güvenli gösteriyordu. Mevduat kaldırıldı (kapsam notu: `gerek.md` §2 onu
varlık sınıfı sayıyor, `scope.yaml` ise iki ayrı listede kapsam dışı
sayıyor; karar bu çelişkiyi giderme yönünde alındı, analist onayı bekliyor).
Para piyasası fonu ise bir yatırımdır — fiyatı oynar (ölçülen %1,42 yıllık)
— ve borçlanma araçlarına taşındı.

Bunun bedeli: `TransactionType.INTEREST` demoda yalnızca mevduat faizinden
üretiliyordu, artık üretilmiyor.

Borçlanma tarafı fonlarla temsil edilir: Türk tahvillerinin ücretsiz güvenilir
bir fiyat kaynağı yok, uydurma ISIN'ler ise hiçbir sağlayıcıdan çekilemediği
için sonsuza kadar bayat kalıyordu. Fon tahvil değildir (vade/kupon yok) ama
tahvil riski taşır ve gerçek fiyatlanır.

### ABD hisseleri ve kur dönüşümü
Evrende 21 ABD hissesi var (AAPL, MSFT, NVDA, … CAT), `currency="USD"`.
Sembole `.IS` eklenmez; yfinance'ta sade koduyla geçerler.

USD varlıkların değeri `valuation_service` içinde **o günün kuruyla** TRY'ye
çevrilir (AK 5.7). Bu yol uzun süre yalnızca `AKE` (eurobond fonu) tarafından
kullanıldı; `test_ak_5_7_fx_conversion` hâlâ onun üzerinden koşuyor, çünkü
tek varlıklı portföyde dönüşümü izole eden en sade örnek odur — ama artık
o kod yolunu 22 varlık paylaşıyor, yani AKE kaldırılsa bile yol ölmez.

**Ölçülen volatiliteler yerli hissenin altında** (ABD ortalaması %28,8'e
karşı BIST %38,6) ve ABD tarafında SRRI gerçekten ayrışıyor: BRK-B %14,7 (5),
KO/PG/MCD ~%19 (6), AMD %72,1 (7). Yerli hissede on beşin on beşi de 7
alıyordu. Buna rağmen risk sıralamasında yabancı hisse yerlinin **bir kademe
üstünde** olacak; gerekçe volatilite değil erişim ve karmaşıklıktır (kur
maruziyeti, sınır ötesi saklama, yerel yatırımcı korumasının bulunmaması,
vergi). Bkz. `providers/universe._foreign_stock`.

### Uygunluk risk seviyesi (1-7)

Anket puanı 1-7; **seviyesi puandan büyük olan varlık** için kullanıcı ne
tavsiye alır ne de portföyünde bulunması uyumlu sayılır
(`services/advice_eligibility.py`).

| Seviye | Ne | Ölçülen volatilite |
|---|---|---|
| 1 | Serbest nakit, para piyasası fonu | %0 · IOO %1,42 |
| 2 | TL borçlanma araçları fonu | AYR %1,5 · APT %7,1 · AK2 %10,0 |
| 3 | Döviz, eurobond fonu | USDTRY ~%1 · AKE %4,6 |
| 4 | Kıymetli maden, altın fonu | gram altın %24 · GTA %25,6 |
| 5 | Yerli hisse, yerli hisse fonu | BIST ort. %38,6 |
| 6 | Yabancı hisse, yabancı hisse fonu | ABD ort. %28,8 |
| 7 | **Serbest fon** (SPK III-52.1) | BHE %22,8 |

**Bu ölçek SRRI değildir.** İkisi de 1-7 olduğu için karıştırılmaya müsait
ama SRRI volatilite bandından hesaplanır; bu tablo *uygunluk* sıralamasıdır
("hangi ürün hangi yatırımcıya sunulabilir"). Volatilite sıralamayı
doğrularken kullanıldı, belirlemedi — **ölçümle bilerek ayrışan iki yer** var
ve ikisi de kodda gerekçesiyle yazılı: döviz TL tahvil fonunun üstünde
(düşük oynaklığı TL'nin düzenli değer kaybının yan ürünü), yabancı hisse
yerlinin üstünde (gerekçe volatilite değil erişim/karmaşıklık).

#### Seviye 7 neden serbest fon
Serbest fonlar yalnızca **nitelikli yatırımcıya** satılır, diğer fon
türlerine uygulanan portföy sınırlamalarının çoğundan **muaftır** ve
izahnameleri **kaldıraç, açığa satış ve türev** kullanımına izin verir.
Yönetici sıradan bir fonun sınırları olmadan strateji değiştirebildiği için,
uygunluk sorusunun cevabı fonun bugünkü içeriğinden bağımsız olarak hayırdır.
Kural: **serbest fon = 7**, ne tutuyor olursa olsun.

700 TEFAS fonu tarandı (26 Ağustos 2026): **kaldıraçlı, ters (inverse) ve
girişim sermayesi fonu sıfır**. 7'nin ilk tanımının ("türev/kaldıraçlı ürün")
TEFAS'ta karşılığı yoktu; serbest fon bu boşluğu doldurabilen tek araç ve
`scope.yaml` onu kapsam içi sayıyor.

Elenen adaylar: `GMI` (Gümüş Serbest) %61,4 ile en oynak adaydı ama
kaldıraçlı değil — **spot gümüşün kendisi %63,1**, rakam emtiadan geliyor.
`THV` %137 ölçtü ama üst üste +%67/+%90 sıçraması var (veri kusuru). On
istatistiksel arbitraj fonu %2,1-4,7: yapıca en karmaşık ürünler ama piyasa
nötr, tepeye konsalar "risk 7 ama hiç oynamıyor" görüntüsü doğardı.

Tablo **26 Ağustos 2026'da yeniden kalibre edildi**. Eski hâli (şartnameden
birebir: NAKIT 1, TAHVIL 3, DOVIZ 4, MADEN 4, HISSE 6) yedi puandan yalnızca
**dört farklı sonuç** üretiyordu — 2, 5 ve 7 puanları bir öncekine hiçbir şey
eklemiyordu. Yeni tabloda **yedi puanın yedisi de** farklı bir varlık kümesi
açıyor.

#### Varlık düzeyi istisnası
Seviye normalde `ASSET_CLASS_ADVICE_RISK_LEVEL[sınıf]`'tan gelir, ama
`AssetSpec.risk_level` doluysa **o kazanır** — iki yöne de:

| Varlık | Sınıfı | Seviyesi | Neden |
|---|---|---|---|
| `IOO` | BOND (2) | **1** | Para piyasası fonu, nakit eşdeğeri |
| `AKE` | BOND (2) | **3** | Eurobond — getirisi ağırlıklı olarak kurdan |
| `AFT` | STOCK (5) | **6** | Yurt dışı hisse fonu |
| 21 ABD hissesi | STOCK (5) | **6** | Sınır ötesi erişim |
| `XAGTRY` `XPTTRY` | PRECIOUS_METAL (4) | **5** | Ölçülen %65,9 / %55,3 — yerli hissenin üstünde |
| `BHE` | STOCK (5) | **7** | Serbest fon — nitelikli yatırımcı, kaldıraç izni |

#### Seed portföyleri puana UYAR
`data/seed_ledger._uygun_arketip` arketipin varlıklarını kullanıcının anket
puanına göre süzer ve kalan ağırlıkları orantılı yeniden dağıtır (nakit
dahil, ki `cash_heavy` nakit ağırlıklı kalsın).

Süzgeç olmadan Ürün Sahibi ilkesi ("profil önce belirlenir, portföy ona göre
kurulur") dummy veride ihlal ediliyordu ve bu **yapısaldı**: dört arketipin
dördünde de hisse, kıymetli maden ve döviz vardı, oysa muhafazakâr bandın
(1-2) izin verdiği tek sınıf tahvil, dengeli bandın (3-4) izin vermediği tek
sınıf hisse. Ölçülen: **31/50 kullanıcı** puanının üstünde varlık tutuyordu,
şimdi **0/50**.

Süzme **varlık** düzeyinde yapılır, sınıf düzeyinde değil: büyüme bandı (5)
hisse sınıfını açar ama ABD hisselerini (6) ve serbest fonu (7) açmaz.

Merdiven demo verisinde görünür hâlde:

| puan | örnek portföy |
|---|---|
| 1 | `IOO` + %66 nakit |
| 2 | `AK2, APT` |
| 3 | `AKE, APT, CHFTRY, GBPTRY, IOO, USDTRY` |
| 4 | `AK2, APT, CEYREK, CHFTRY, CUMHUR, EURTRY, GBPTRY, IOO` |
| 5 | `APT, CEYREK, EREGL, EURTRY, FROTO, GBPTRY, IOO, TURSG, XAGTRY` |
| 6 | `ANSGR, EURTRY, GRTHO, META, TAMALTIN, WMT` |
| 7 | `BHE, EUREN, EURTRY, KO, NVDA, YARIM` |

#### Tepe kademe garantisi
Uyumluluk yetmiyor: üst kademenin gerçekten TUTULUYOR olması da gerekiyor.
Süzgeç doğru çalışırken bile seçim aday havuzunda düzgün dağılımlıydı ve üst
kademeler havuzda azınlıkta — hisse sınıfında **101 yerliye karşı 21 ABD
hissesi ve tek bir serbest fon**. Ölçülen: 6-7 puanlı 13 kullanıcının yalnızca
5'i yabancı varlık tutuyordu, `BHE`'yi **hiç kimse** tutmuyordu. 5, 6 ve 7
puanlı portföyler ekranda ayırt edilemiyordu.

`_tepe_temsil_edilsin` kullanıcının erişebildiği en üst kademeden en az bir
varlık seçilmesini garantiliyor. Aşağı kademelerde neredeyse işlemsiz (4
puanlının tepesi kıymetli madendir ve o sınıfta zaten her varlık o
kademededir); ısırdığı yer yalnızca 6 ve 7. Sonuç: **7/7** altı puanlı yabancı
varlık, **6/6** yedi puanlı `BHE` tutuyor.

`MIN_HOLDINGS_PER_USER` bu yüzden 5'ten **1'e** indi: 1 puanlık kullanıcının
alabileceği tek varlık `IOO`. Eksiklik değil, kuralın kendisi.

#### Anket puanı nerede duruyor
`users.risk_survey_score` (1-7, nullable, CHECK'li). **Puan yetkili alan,
`users.risk_profile` ondan türer** (`config.risk_profile_for_survey_score`):
1-2 Muhafazakâr · 3-4 Dengeli · 5 Büyüme · 6-7 Agresif. Bantlar bu merdivenle
hizalı seçildi, her profil kendi bandının açtığı varlık kümesiyle örtüşüyor.

`NULL` anlamlıdır: "kayıtlı anket sonucu yok". `make seed` 50 demo
kullanıcısının hepsini dolduruyor ve **yedi puanın yedisini de** temsil
ediyor. Yazma yolu `services/user_service.set_user_risk_survey`; uçlar
`docs/API.md` → "Kullanıcı risk profili ve anket puanı".

#### Seviye DB'de de var: `assets.risk_level`
Sütun 1-7 tutar, CHECK'li, `seed_assets` her koşuda **koddan yeniden yazar**.
Böylece seviye SQL'den sorgulanabiliyor ve JOIN'e girebiliyor:

```sql
-- puanı 3 olan kullanıcıya yasak varlıklar
SELECT symbol, risk_level FROM assets WHERE is_active AND risk_level > 3;
```

**TÜREV KOPYADIR, ikinci bir gerçek değil.** Tanım noktası hâlâ
`universe.py` + `config.py`; sütuna elle yazılan değeri bir sonraki
seed/backfill üzerine yazar. Ayrışma olursa `scripts/data_doctor` §7
bildirir ("risk seviyesi DB ile kod arasinda ayrismis").

Neden kopya tutuluyor: alım/satım engeli ve risk ajanı bu bilgiye **DB
üzerinden** bakacak. Yalnızca kodda kaldığı sürece `assets` tablosuna bakan
biri alanın var olduğunu bile göremiyordu.

`NULL` yalnızca **pasif** (evrenden çıkarılmış) varlıklarda olabilir; aktif
varlıkta NULL bir kusurdur ve testle korunur.

Okuma noktası (kod tarafı) `advice_eligibility.asset_risk_level(symbol, asset_class)`;
sınıf sürümü (`is_advice_allowed`) kaba görünüm içindir ve şartname metnine
bire bir karşılık geldiği için korunuyor. Bir varlığa karar verirken
**varlık sürümü** kullanılmalı.

`IOO`'nun 1'e çekilmesi zorunluydu: nakit sınıfında varlık yok, dolayısıyla
o istisna olmadan 1 puanlık kullanıcıya önerilebilecek hiçbir varlık
kalmıyordu.

### Yeni varlık eklemek
`backend/app/providers/universe.py` → `ASSET_UNIVERSE`'e bir `AssetSpec`
satırı ekleyin, `make seed` çalıştırın. **Başka hiçbir kod değişmez.**
Sağlayıcı eşlemesi (`data_source`, `provider_symbol`) spec'in içindedir.

**`base_price` uydurulmaz, ölçülür.** Sentetik serinin başlangıç değeridir;
gerçek fiyattan kat kat saparsa çevrimdışı kurulum gerçekle alakasız bir
evren üretir. Varlığın gerçek verisi varsa serinin İLK gerçek fiyatı okunur
(bugünkü değil — `base_price` serinin başıdır); sorgu `universe.py`'nin
başındaki not içinde. `test_fon_base_price_gercek_fiyatla_ayni_mertebede`
ölçülen değerleri kilitler.

**Varlık sınıfının tipik davranışından ayrılıyorsa** `synthetic_daily_drift`
ve `synthetic_daily_volatility` ile sınıf varsayılanı ezilir. Tek örneği
`IOO` (para piyasası fonu): borçlanma fonlarıyla aynı sınıftadır ama
oynaklığı belirgin biçimde düşüktür (ölçülen %1,42 yıllık).

**TEFAS kodları anlamlı kısaltma DEĞİLDİR.** Bir kez tam bu yüzden yanlış
varlık evrene girdi: `PPF` kodu "Para Piyasası Fonu" diye okunmuştu, oysa o
kod *Azimut Portföy Akçe Serbest Fon*'a ait ve ölçülen oynaklığı %5,3.
Fon eklerken kodu TEFAS'tan doğrulayın, adından çıkarmayın.

**Fon eklerken sınıfı elle vermeyin:** `_fund()` varlık sınıfını alt türden
türetir (`_FUND_ASSET_CLASS`). Fonun ekonomik riski neyse sınıfı odur — para
piyasası fonu `CASH`, altın fonu `PRECIOUS_METAL`, borçlanma araçları fonu
`BOND`. Eskiden tüm fonlar `STOCK` idi; altın fonu ve para piyasası fonu
FR-4'ün "Hisse → Yüksek" risk etiketini alıyor, risk motorunda savunma
tarafında (`BOND`+`CASH`) sayılması gereken enstrüman hisse riski taşıyor
görünüyordu.

### Yeni veri sağlayıcısı eklemek
1. `backend/app/providers/` altına yeni dosya: `fetch_series`/`fetch_latest`
   sunan bir sınıf (bkz. `base.py` sözleşmesi; `tcmb.py` örnek).
2. `config.py`'deki `PriceSource`'a değer + `PRICE_SOURCE_PRIORITY`'ye öncelik
   ekleyin (migration: enum'a değer eklemek gerekir — `d17f3b9e5c28`'deki tip
   yeniden yaratma kalıbını kopyalayın).
3. `registry.py`'de ilgili zincire yerleştirin.

### İşlem kaydetmek (ajan/API kodu)
```python
from app.services.ledger_service import record_transaction, rebuild_holdings

record_transaction(db, portfolio_id, TransactionType.BUY,
                   transaction_date=..., asset_id=..., quantity=..., price=...,
                   fx_rate_to_try=...)   # nakit ayağı otomatik hesaplanır
rebuild_holdings(db, portfolio_id)       # önbelleği tazele
```

### Portföy okumak
- Özet: `portfolio_service.get_portfolio_summary` (kur dönüşümü + nakit dahil)
- Tarihsel değer/getiri: `valuation_service.value_series` / `twr`
- Kâr/zarar: `valuation_service.realized_pnl` / `unrealized_pnl`
- Pozisyon/nakit (tarihli): `ledger_service.position_as_of` / `cash_balance_as_of`

## 5. Seed ve determinizm

- `SEED=42` — kullanıcılar, profiller, arketipler, işlem günleri ve miktarlar
  her çalıştırmada aynı üretilir.
- **Ankraj (seed'in "bugün"ü) artık sabit değil.** Varsayılan olarak
  veritabanındaki en son **gerçek** fiyat gününe bağlanır; böylece defter
  fiyatların bittiği gün biter ve aradaki açık **yapısal olarak sıfır** olur
  (ölçüldü: 0 gün). Sabit tarih gerekiyorsa `ANCHOR_DATE` her şeyi ezer —
  testler bunu kullanıyor (`tests/conftest.py`, 2026-08-01).

  Eskiden sabitti (2026-08-01) ve gerçek fiyatlar günlük toplama işiyle
  ilerlediği için açık **her gün bir gün** büyüyordu: 23 Ağustos'ta 21 güne
  çıkmıştı, "Son İşlemler" listesindeki her kayıt üç haftalık görünüyordu ve
  kapatmak için birinin `.env`'i elle güncelleyip yeniden seed etmesi
  gerekiyordu. Gerekçesi yeniden üretilebilirlikti ama zaten korumuyordu:
  iki farklı günün seed'i, fiyatlar farklı olduğu için nasılsa aynı çıkmıyor.
  Ayrıntı ve çözüm sırası: `data/anchor.py`.

  **Sentetik satırlar ankrajı ilerletmez** — onların son günü zaten bir
  önceki ankrajdan geliyor; ölçüt alınsaydı ankraj kendi kuyruğunu yer ve
  hiç ilerlemezdi.
- **Kullanıcı kimlikleri de tohuma bağlıdır.** Model varsayılanı `uuid.uuid4`
  işletim sisteminin rastgeleliğini kullanır ve SEED'den etkilenmez; isimler
  ve portföyler aynı üretilirken kimlikler her seed'de değişiyordu.
  `seed_ledger._user_id` bunu `uuid5(USER_UUID_NAMESPACE, f"user-{i}")` ile
  sabitler. **`USER_UUID_NAMESPACE` değiştirilmemeli** — değişirse tüm
  kullanıcı UUID'leri değişir ve elde tutulan bağlantılar ölür.
- **Risk profili, arketipten TÜRETİLİR** (`ARCHETYPE_RISK_PROFILE`,
  `seed_ledger._build_archetype_risk_profiles`). ÜRÜN SAHİBİ KARARI (Not 5,
  2026-08): dört arketip, hisse ağırlığına göre artan sırada, dört risk
  profiliyle (yine artan risk sırasında) birebir eşlenir — `cash_heavy`→
  conservative, `diversified`→balanced, `mixed`→growth,
  `concentrated_equity`→aggressive. Böylece GROWTH dahil dört profilin
  tamamı üretilir ve hiçbir kullanıcının portföyü kendi profilinin Hisse
  üst sınırını (`RISK_MAX_CATEGORY_WEIGHT`) aşmaz — dummy veri artık gerçek
  kullanıcı akışıyla aynı ilkeye (Not 3/4: "profil önce, portföy ona göre")
  uyar.
  Önceki tasarım (`_profile_and_archetype`, AK-2.6) profili arketipten
  BAĞIMSIZ, farklı hızda bir sayaçla döndürüyordu ve kasıtlı olarak
  uyumsuz kombinasyonlar da üretiyordu (risk motorunun uyumsuzluk-uyarısı
  yolunu dummy veriyle sergileyebilmek için). PO bu kararı geri aldı;
  uyumsuzluk-uyarısı yolu artık kendi birim testleriyle
  (`tests/test_risk_service.py`) doğrulanıyor.
- Fiyatlar yalnızca **işlem günlerinde** (hafta içi) üretilir; gerçek
  kaynaklarla takvim uyumu için.
- Sentetik fiyatlar üç bileşenli **faktör modeli** kullanır (piyasa + sınıf +
  varlığa özgü); piyasa faktörü, DB'de gerçek USDTRY serisi varsa ondan
  türetilir. Korelasyonlar `test_synthetic_correlation_nonzero` ile korunur.
- `python -m data.generate_dummy` varsayılan olarak yalnızca kullanıcı
  tablolarını + sentetik fiyatları tazeler; `--wipe-all` her şeyi siler.

## 6. Değişmezler ve testleri (`tests/test_data_layer.py`)

| Değişmez | Test | Kriter |
|---|---|---|
| holdings == defterden yeniden üretilen | `test_ledger_reconciliation` | AK 5.12 |
| Nakit asla negatif değil | `test_cash_never_negative` | — |
| Sentetik gerçeği ezemez | `test_synthetic_never_overwrites_real` | AK 5.1/5.5 |
| Her fiyatta kaynak + zaman | `test_ak_5_3_price_source_and_timestamp` | AK 5.3 |
| USD varlık güncel kurla TRY'ye | `test_ak_5_7_fx_conversion` | AK 5.7 |
| DEPOSIT getiri sayılmaz (TWR) | `test_external_flow_excluded_from_return` | FR-3 |
| Türetilmiş fiyat = kaynak × katsayı | `test_derived_price_matches_factor` | — |
| Sentetik korelasyon ≠ 0 | `test_synthetic_correlation_nonzero` | AK-2.2/2.6 |

## 7. Şema özeti (migration zinciri)

`60bf3d7b4c54 → abe38b185ff1 → 9c31e7a0d2b4 → 4e8b2f6c1a53 → d17f3b9e5c28 →
6a92d4c8e0f1 → b26e8dab6ef9 → c5d81a3f7b60 → f18c4a2e7b90 → a3d75e1c9f04`

- `users` +risk_profile · `assets` +sub_type/is_active/data_source/
  provider_symbol/derived_from/derived_factor
- `price_history` +source/fetched_at, 18,6 hassasiyet
- `transactions` 7 tip + nakit ayağı + kur + CHECK'ler + indeksler
- `holdings` +realized_pnl_try/last_rebuilt_at (qty=0 satır silinmez)
- `data_ingest_log` (yeni): çekim işlerinin iş-düzeyi kaydı
- `risk_profile` enum'una `growth` (`b26e8dab6ef9`)
- `users` +national_id/password_hash/last_login_at (`c5d81a3f7b60`)
- `users` +risk_survey_score, 1-7 CHECK'li, nullable (`f18c4a2e7b90`)
- `assets` +risk_level, 1-7 CHECK'li; migration mevcut satırları da doldurur (`a3d75e1c9f04`)

## 8. Sık düşülen tuzaklar

- **PG enum'una `ADD VALUE` ile eklenen değer aynı transaction'da
  kullanılamaz.** Migration'da yeni değere başvuracaksanız tip yeniden
  yaratma kalıbını kullanın (`d17f3b9e5c28`).
- **Testler migration koşmaz** (`Base.metadata.create_all` + SQLite): CHECK
  kısıtlarını hem modele hem migration'a yazın.
- **`holdings.quantity == 0` satırı silmeyin** — gerçekleşmiş K/Z oradadır.
- **Tarihsel değerlemede bugünün kurunu kullanmayın**; `valuation_service`
  o günün kurunu kullanır, siz de öyle yapın.
