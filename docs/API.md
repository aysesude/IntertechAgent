# API Sözleşmesi

Şemaların tanımlı olduğu yer: `backend/app/schemas/`. Frontend tipleri
(`frontend-v2/src/api/`) bunlarla birebir eşleşmelidir.

## Kimlik doğrulama (FR-0 / AK 5.4)

`/health` ve `POST /api/auth/login` DIŞINDAKİ tüm uçlar `Authorization: Bearer
<token>` başlığı ister. Kullanıcıya özel uçlar ayrıca yoldaki/gövdedeki
`user_id`'nin token sahibiyle aynı olmasını şart koşar.

| Kod | Anlamı | Arayüz ne yapmalı |
|---|---|---|
| `401` | Token yok, bozuk ya da süresi dolmuş | Giriş ekranına dön |
| `403` | Token geçerli ama bu veri başkasının | "Erişim yetkiniz yok" göster |

Kimlik, yol imzalarını değiştirmedi (`/api/portfolio/{user_id}` aynı kaldı):
`/me` kalıbına geçmek MCP tool'larını, ajanları ve bu dokümanı topluca
kırardı. Yoldaki değer artık yalnızca **doğrulanan bir iddiadır**.

### `POST /api/auth/login`

```json
{ "national_id": "20433218148", "password": "460213" }
```

```json
{
  "access_token": "<imzalı JWT>",
  "token_type": "bearer",
  "expires_in": 28800,
  "user": {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "full_name": "Elif Yıldırım",
    "risk_profile": "balanced"
  }
}
```

Örnekte gerçek bir token yok: gitleaks JWT biçimli dizeleri sızmış kimlik
bilgisi sayıp CI'ı kırıyor (ölçüldü, `.github/workflows/ci.yml`).

- **Hatalı kimlik ile hatalı şifre AYNI 401'i döner** (`"T.C. kimlik numarası
  veya şifre hatalı."`). Ayrıştırılsaydı hangi numaraların kayıtlı olduğu tek
  tek denenerek çıkarılabilirdi. Kullanıcı bulunamadığında bile bir kukla
  bcrypt doğrulaması yapılır — yanıt süresinden de bilgi sızmasın diye.
- `expires_in` saniyedir ve sunucudan gelir; istemci kendi süre hesabını
  yapmamalıdır.
- `user` aynı yanıtta döner ki arayüz giriş sonrası ikinci bir istek atmasın.
- Yanıt **e-posta ve T.C. kimlik numarası içermez**: arayüzün ikisine de
  ihtiyacı yok.
- 11 haneden farklı bir numara `422` ile reddedilir. Sağlama (checksum)
  doğrulaması BİLEREK yapılmaz — geçersiz numara zaten eşleşmez ve ayrı bir
  hata "bu numara kayıtlı mı" sorusuna dolaylı cevap verirdi.

**Demo kullanıcıları:** T.C. kimlik numaraları `make seed` ile deterministik
olarak üretilir (sağlaması geçerli), şifre `.env`'deki `DEMO_USER_PASSWORD`'dür
ve hepsinde aynıdır. Listeyi görmek için: `make demo-users`.

Kayıt, şifre değiştirme ve şifre sıfırlama uçları **yoktur**. Çıkış (logout)
ucu da yoktur ve gerekmez: token durumsuzdur, çıkış istemcinin token'ı
silmesidir.

### Şifre yenileme (DEMO akışı)

**TEMSİLİ olan:** e-posta gönderilmez, kod sunucuda üretilmez ve saklanmaz —
`DEMO_RESET_CODE` ile eşleşen sabit kod kabul edilir.
**GERÇEK olan:** şifre bcrypt ile özetlenip veritabanına yazılır; kullanıcı
bundan sonra yeni şifresiyle giriş yapar, eskisiyle yapamaz.

#### `POST /api/auth/password-reset/request`

```json
{ "national_id": "20433218148" }
```

```json
{ "code_length": 6, "expires_in_seconds": 180 }
```

- Kimliğin **kayıtlı olup olmadığına bakmadan** aynı yanıtı döner; aksi halde
  bu uç, hangi numaraların sistemde olduğunu tek tek denemeye açık bir araca
  dönüşürdü (giriş ucundaki gerekçenin aynısı).
- **Kodun kendisi dönmez.** Yanıt yalnızca arayüzün alan uzunluğunu ve geri
  sayımı sabit yazmaması için bu iki değeri taşır.

#### `POST /api/auth/password-reset/complete`

```json
{ "national_id": "20433218148", "code": "123456", "new_password": "778899" }
```

Başarıda `204` (gövde yok). Hatalı kimlik ile hatalı kod **aynı `401`'i** döner.

- `new_password` **6 haneli ve yalnızca rakam** olmak zorunda: giriş ekranının
  kabul ettiği biçim bu. Aksi halde kullanıcı, sonradan giriş yapamayacağı bir
  şifre belirlerdi.
- Kod karşılaştırması sabit zamanlı (`secrets.compare_digest`).

**⚠️ GÜVENLİK SINIRI.** Bu uçlar kimlik doğrulaması İSTEMEZ: T.C. kimlik
numarasını ve kodu bilen biri o hesabın şifresini değiştirebilir — kimlik
doğrulamasının etrafından dolaşan bir kapıdır. Sentetik demo verisiyle çalışan,
süreli bir gösterim için kabul edildi. Gerçek bir dağıtımda
`DEMO_PASSWORD_RESET_ENABLED=false` yapılmalı (uçlar `404` döner).

**Bilinen sınır:** yenileme sonrası eski token'lar geçersizleşmez. Bunun için
token kara listesi ya da özete bağlı bir doğrulama gerekir; 8 saatlik demo
token'ı için karşılığı olmayan bir karmaşıklık.

### `GET /api/auth/me`

Token'ın hâlâ geçerli olup olmadığını ve kime ait olduğunu döner (`AuthUser`
gövdesi, yukarıdaki `user` alanıyla aynı). Arayüz sayfa yenilendiğinde bunu
çağırır. Token yoksa `401` + `WWW-Authenticate: Bearer`.

### Geçiş bayrağı: `AUTH_ENFORCE`

Varsayılanı `true` — unutulursa auth **açık** kalır. `false` iken token
GÖNDERMEYEN istekler geçer (token gönderilirse yine doğrulanır).

**Bu bayrağın varlık sebebi kalmadı.** Tek gerekçesi, token göndermeyen eski
`frontend/` ile çalışmayı sürdürebilmekti; o arayüz kaldırıldı ve tek arayüz
olan `frontend-v2` her istekte token gönderiyor.

Silinmesi AYRI bir iş olarak bırakıldı, arayüz kaldırma işine eklenmedi:
bayrak güvenlik davranışını değiştiriyor ve bir ortamın `.env`'inde `false`
duruyorsa silmek o ortamda auth'u aniden zorunlu kılar. Kaldırmadan önce her
ortamda değerinin `true` olduğu doğrulanmalı.

## REST

### `GET /api/portfolio/{user_id}`

```json
{
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "as_of": "2026-08-20",
  "oldest_price_date": "2026-08-20",
  "total_value": 2681069.66,
  "total_cost_basis": 1682346.32,
  "net_invested": 1870000.00,
  "total_gain_loss": { "amount": 811069.66, "percent": 43.37 },
  "allocation": [
    { "asset_class": "stock", "value": 1194764.65, "percent": 44.56 },
    { "asset_class": "precious_metal", "value": 452028.34, "percent": 16.86 },
    { "asset_class": "currency", "value": 356314.16, "percent": 13.29 },
    { "asset_class": "bond", "value": 279635.57, "percent": 10.43 },
    { "asset_class": "cash", "value": 398326.94, "percent": 14.87 }
  ],
  "holdings_count": 10
}
```

404 → `{"detail": "Portfolio not found for user_id ..."}`

**`as_of` ile `oldest_price_date`:** özet her varlığı KENDİ son fiyatıyla
değerler, dolayısıyla tek bir tarih tüm portföyü tarif etmez. `as_of` en
yenisini, `oldest_price_date` en eskisini verir. **İkisi farklıysa arayüz
bunu belirtmelidir** — yalnızca `as_of` gösterilirse özet olduğundan taze
görünür. Hiç fiyatlı varlık yoksa `oldest_price_date` `null` döner.

**`oldest_price_date` yalnızca PİYASA fiyatı olan varlıkları sayar.** Mevduatın
birim fiyatı tanımı gereği 1 TL'dir ve hiç güncellenmez; hesaba katıldığında
tazelik uyarısı HER kullanıcıda kalıcı olarak çıkıyordu (ölçüldü: `as_of`
21.08 iken `oldest` 31.07). Mevduat eskimiyor, sabit — uyarının anlamlı
kalması için yalnızca gerçekten geride kalabilecek varlıklara bakılıyor
(`assets.sub_type` ile ayırt ediliyor).

**İki taban vardır, karıştırılmamalıdır:**

| Alan | Ne | Serbest nakit |
|---|---|---|
| `total_cost_basis` | Elde tutulan varlıkların maliyeti | **hariç** |
| `net_invested` | Dışarıdan konan net sermaye (yatırma − çekme) | **dahil** |

`total_gain_loss.amount` = `total_value - net_invested`. Arayüz kullanıcıya
taban olarak `net_invested`'ı ("Yatırılan tutar") göstermelidir;
`total_cost_basis` gösterilirse üç rakam birbirini tutmaz ve aradaki fark
(yatırıma dönüşmemiş nakit) açıklamasız kalır.

**`total_gain_loss.percent`'in paydası farklıdır: toplam YATIRILAN tutar**
(yalnızca yatırmalar, çekimler düşülmeden). Çekim yapılmamış portföyde ikisi
eşittir, ayrıştığında net sermaye yanlış cevap verir:

```
1.000 yatır → 1.500'e çıkar → 500 çek → değer 1.000
kazanç              = 500        (doğru)
net sermayeye göre  = %100       (yanlış: para %50 büyüdü)
toplam yatırılana   = %50        (doğru)
```

Ayrıca payda hiçbir zaman negatif olamaz; çekim yatırımı aşarsa
`net_invested` negatife düşüyor ve oran anlamsızlaşıyordu.

Taban neden maliyet değil: hesapta duran para da kullanıcının koyduğu paradır,
kazanç değildir. Maliyet taban alındığında serbest nakdin tamamı kâr olarak
raporlanıyordu (ölçüldü: 1.87M yatırmış bir portföyde 187.654 TL nakit,
getiriyi %43,37 yerine %59,36 gösteriyordu). Temettü ve mevduat faizi ise dış
akış olmadığı için bu farkta doğru biçimde kazanç tarafında kalır.

Not: sayısal alanlar hesaplamada `Decimal` ile tutulur, JSON'a `float` olarak
serialize edilir (bkz. `app/schemas/portfolio.py`'deki `Money` tipi) — string
değil, frontend doğrudan `number` olarak tüketir.

### Dashboard uçları

Aşağıdaki uçların hiçbiri **ajan çağırmaz**, servisleri doğrudan okur (Diyagram
01/03). Dashboard açılışında sorulmuş bir soru ve anlatılacak bir şey yok; araya
LLM koymak ekranı model hızına bağlar ve halüsinasyon yüzeyi açar. Ajanlar
yalnızca `POST /api/chat` yolunda devrededir.

Ortak hata kodları — üçü farklı şeydir, arayüz üçünü ayrı göstermelidir:

| Kod | Anlamı |
|---|---|
| `404` | Kullanıcı ya da portföy yok |
| `422` | İstek hatalı (ör. `start_date > end_date`, geçersiz tarih biçimi) |
| `409` | Kaynak var, hesaplanacak veri yok (hiç işlem yok, pencerede fiyat yok) |

#### `GET /api/portfolio/{user_id}/holdings`

Varlık tablosu: TRY değer, ağırlık, ortalama maliyet, gerçekleşmiş/gerçekleşmemiş K/Z.

```json
{
  "user_id": "3fa85f64-...",
  "as_of": "2026-08-20",
  "holdings": [
    {
      "symbol": "TUPRS", "name": "Tüpraş", "asset_class": "stock", "currency": "TRY",
      "quantity": 1428.0, "current_price_try": 391.75, "market_value_try": 559419.0,
      "weight_percent": 33.84, "avg_cost_try": 172.63, "cost_basis_try": 246515.64,
      "unrealized_pnl_try": 312903.36, "unrealized_pnl_percent": 126.91,
      "realized_pnl_try": 0.0, "price_missing": false
    }
  ],
  "best_performer": { "symbol": "CUMHUR", "name": "Cumhuriyet Altını", "unrealized_pnl_percent": 201.46 },
  "worst_performer": { "symbol": "SASA", "name": "Sasa Polyester", "unrealized_pnl_percent": -82.67 },
  "excluded_symbols": []
}
```

- Fiyatı ya da kuru bulunamayan varlık **listeden düşmez**: `price_missing: true`
  ile döner, değer alanları `null` kalır ve ağırlık paydasına girmez. Eksik veriyi
  `0` ile doldurmak sessizce yanlış sayı üretmek olurdu.
- `weight_percent` paydası **nakit dahil** toplam portföy değeridir —
  `get_portfolio_summary.total_value` ile aynı payda, böylece pasta grafiğindeki
  sınıf ağırlıklarıyla tutarlı. Sonuç: satırlar `100`'e değil, `100 − nakit%`
  değerine toplanır.
- `best_performer` / `worst_performer` **kodda** seçilir. Dil modelinin iki satırı
  karşılaştırıp "en çok kazandıran bu" demesi hesaplama sayılır ve yasaktır.

#### `GET /api/portfolio/{user_id}/performance?window=1m`

Değer serisi + kümülatif yatırılan para. `window`: `1m` | `3m` | `6m` | `12m`.

```json
{
  "user_id": "3fa85f64-...", "as_of": "2026-08-20", "window": "3m",
  "granularity": "daily", "inception": "2025-08-05", "truncated_to_inception": false,
  "series": [{ "date": "2026-05-22", "value_try": 1410924.92, "invested_try": 1460000.0 }],
  "summary": {
    "start_value": 1410924.92, "end_value": 1653329.29,
    "change_amount": 242404.37, "change_percent": 17.18,
    "realized_pnl": 0.0, "unrealized_pnl": 179532.29,
    "changes": { "daily": 2.21, "weekly": 4.88, "monthly": 10.05 }
  }
}
```

- `change_amount` ve `change_percent` **dış akıştan arındırılmıştır**:
  `change_amount = (son değer − ilk değer) − dönem içi net para giriş/çıkışı`,
  `change_percent = TWR`. Ham değer farkı kullanılsaydı 100.000 TL yatıran
  kullanıcı hiçbir şey kazanmadan "kâr ettim" görürdü.
- Grafikteki `value_try` ↔ `invested_try` boşluğu ham hâliyle durur; toplam kâr
  oradan okunur. `invested_try` portföyün başından beri sayılır, pencere başında
  sıfırlanmaz.
- Seri **son fiyat gününde** biter, bugünde değil. Fiyat hattı geride kalmışsa
  bugüne uzatmak, son bilinen fiyatı tekrar çizip "değer değişmedi" yanılsaması
  üretirdi.
- Hafta sonları seride yer almaz. Akış birikimi tüm günler üzerinden yapıldığı
  için cumartesi yatırılan para kaybolmaz.
- `granularity` AUTO çözülür: `1m/3m/6m` → `daily`, `12m` → `weekly`. Kova
  indirgemesinde o kovanın **son** günü alınır, ortalama alınmaz — ortalama hiç
  var olmamış bir değer üretir.
- `changes.daily/weekly/monthly` için yeterli geçmiş yoksa `null` döner, `0` değil.

#### `GET /api/portfolio/{user_id}/transactions?start_date=&end_date=&symbols=`

Alım/satım işaretçileri ve nakit hareketleri, eskiden yeniye sıralı.

```json
{
  "user_id": "3fa85f64-...", "start_date": null, "end_date": null,
  "transactions": [
    {
      "transaction_date": "2025-09-08T10:00:00Z", "type": "buy", "symbol": "TUPRS",
      "quantity": 467.0, "price": 175.88, "currency": "TRY", "fx_rate_to_try": 1.0,
      "fee_try": 82.13, "cash_amount_try": -82134.81, "position_after": 467.0
    }
  ]
}
```

- `position_after` işlemden sonraki toplam pozisyondur ve **defterin başından**
  sayılır. Tarih süzgeci uygulansa bile pencere öncesindeki alımlar sayılır;
  aksi halde pozisyon olduğundan küçük çıkardı.
- `symbols` verilmezse nakit hareketleri (`deposit`/`withdraw`/`fee`/`interest`)
  de listeye girer; verilirse yalnızca o sembollerin işlemleri döner.
- `cash_amount_try` işaretlidir ve işlem anındaki kurla dondurulmuştur: o gün
  hesaptan fiilen çıkan veya giren TL budur.

#### `GET /api/portfolio/{user_id}/benchmark?window=3m`

Portföy getirisi ↔ endeksler (bar grafiği).

```json
{
  "user_id": "3fa85f64-...", "window": "3m",
  "start_date": "2026-05-22", "end_date": "2026-08-20", "truncated_to_inception": false,
  "portfolio_return_percent": 20.04,
  "by_asset_class": [
    { "asset_class": "stock", "return_percent": 32.47 },
    { "asset_class": "precious_metal", "return_percent": 5.68 }
  ],
  "benchmarks": [
    { "symbol": "XAUTRY", "name": "Gram Altın", "return_percent": 5.68 },
    { "symbol": "USDTRY", "name": "Amerikan Doları", "return_percent": 4.90 }
  ],
  "excluded_symbols": []
}
```

Metrik — pencere başındaki (`t0`) miktarlar **sabit tutulur**, yalnızca fiyat
değişimi ölçülür:

```
C = Σ qᵢ(t0) × pᵢ(t0)      V = Σ qᵢ(t0) × pᵢ(t1)      getiri% = 100 × (V / C − 1)
```

- Pencere içindeki alım/satım, temettü ve komisyon hesaba **katılmaz**; endeksin
  saf fiyat getirisiyle aynı ölçekte olması için. Aksi halde "portföyüm endeksi
  yendi" cümlesi, aslında sadece yeni para yatırıldığı anlamına gelirdi.
- Bu yüzden bu uçtaki getiri, `/performance`'taki TWR ile **kasıtlı olarak
  farklıdır**. TWR nakit yükünü ve dönem içi işlemleri içerir, bu metrik içermez.
- `t0` fiyatı bulunmayan varlık dışlanır ve `excluded_symbols` ile bildirilir.
- Endeksler: `XU100`, `XAUTRY`, `USDTRY`. **`XU100` varlık evreninde henüz
  tanımlı değil** (`app/providers/universe.py`), o yüzden listede görünmüyor;
  eklendiği gün (`provider_symbol: "XU100.IS"`) kod değişmeden listeye girer.

#### `GET /api/prices/history?symbols=TUPRS&symbols=XAUTRY&window=3m`

Sembol bazlı kapanış serisi. `granularity`: `auto` | `daily` | `weekly` |
`monthly`, `currency`: `try` | `native`.

```json
{
  "as_of": "2026-08-20", "window": "3m", "granularity": "daily", "currency": "try",
  "requested_start": "2026-05-22", "actual_start": "2026-05-22",
  "series": { "TUPRS": [{ "date": "2026-05-22", "close": 243.10 }] },
  "unknown_symbols": ["YOKBOYLE"],
  "symbols_without_data": []
}
```

- **Canlı fiyat değildir.** Veriler günlük toplama işiyle yazılır
  (`app/services/price_ingest.py`, `make daily-update`); bu uç internete çıkmaz.
  `as_of` verinin hangi güne ait olduğunu bildirir.
- **Kısmi veri hata değildir.** Pencerenin tamamı veritabanında yoksa eldeki
  kadarı döner, `actual_start` gerçek başlangıcı bildirir. Bir sembolün verisinin
  olmaması diğerlerinin serisini engellemez; o sembol `symbols_without_data` ile
  raporlanır. Hepsi birden boşsa `409`.
- `currency=try` çevirimi **o günün** kuruyla yapılır; bugünkü kurla geçmişi
  çevirmek tarihsel değeri bozar. `native` çevirim yapmaz.

### Al / Sat (`/api/trade`)

Projedeki **ilk para hareket ettiren** uç ailesi. Dördü de
`verify_user_access` ister (AK 5.4) — başkasının portföyünde işlem yapmak bu
projedeki en ağır yetki ihlali olurdu.

**FİYAT İSTEK GÖVDESİNDE ALINMAZ.** İstemciye fiyat yazdırmak, tarayıcı
üzerinden istenen fiyattan alım yapmaya açık kapı bırakırdı; fiyat her zaman
sunucudaki son kapanıştan okunur.

#### `GET /api/trade/{user_id}/assets`

Ekranın listesi: varlıklar, son kapanış, uygunluk, eldeki miktar, nakit.

```json
{
  "survey_score": 5, "cash_balance": 100000.0,
  "assets": [{
    "symbol": "AAPL", "name": "Apple", "risk_level": 6,
    "price": 200.0, "price_date": "2026-08-27", "price_stale": false,
    "can_buy": false,
    "block_reason": "Bu varlığın risk seviyesi 6, sizin anket puanınız 5. …",
    "held_quantity": 0, "quantity_step": 1
  }]
}
```

Uygun olmayan varlıklar listeden **düşmez**, `can_buy=false` +
`block_reason` ile döner. Sessizce elemek, kullanıcının o varlığın var
olduğunu bile görmemesi demek olurdu.

#### `POST /api/trade/{user_id}/preview`

`{ "symbol": "THYAO", "side": "buy", "quantity": 10 }` → ne ödeneceği,
komisyon, işlem sonrası bakiye ve pozisyon. **Deftere yazmaz.**

Miktar sınıfın hassasiyetine **aşağı** yuvarlanır (hisse tam sayı, maden
0,01) ve yuvarlanmış hâli yanıtta döner — kullanıcının yazdığından farklı
olabilir ve bu gösterilmeli. Yukarı yuvarlamak istemediği kadar alım
yaptırırdı.

#### `POST /api/trade/{user_id}/execute`

Aynı gövde; emri deftere yazar ve `holdings` önbelleğini yeniden kurar.
Doğrulamaların tamamı `preview` ile **aynı yoldan** geçer — iki ayrı kontrol
listesi olsaydı biri güncellenip diğeri unutulurdu.

#### `POST /api/trade/{user_id}/deposit`

`{ "amount": 50000 }` → yeni bakiye. **Gerçek bir ödeme akışı değildir;**
bakiyesi biten kullanıcının demo akışında kilitlenmemesi için var.

#### Kurallar

- **Alım engellenir, satım asla.** Puanının üstündeki varlık alınamaz ama
  elindeki her zaman satılabilir — uyumsuzluktan çıkışın tek yolu odur.
- **Kur işlem anında dondurulur** (`transactions.fx_rate_to_try`). Sonradan
  hesaplansaydı geçmiş bir alımın TRY maliyeti bugünkü kura göre değişir ve
  kâr/zarar oynardı.
- **Komisyon yok** (ürün kararı, 27 Ağustos 2026).
- **İşlem tarihi bugündür**, fiyat son kapanış. Cron akşam koştuğu için
  sabah/hafta sonu yapılan işlemde ikisi farklı güne düşebilir; `price_date`
  ve `price_stale` bunu söyler, arayüz göstermek zorundadır.
- Fiyatı olmayan varlık **işlem görmez** — fiyat uydurulmaz (AK 5.5).
- Defter kuralı ihlalleri (`LedgerError`) **422** döner: kullanıcının
  düzeltebileceği bir durumdur, sunucu hatası değil.

**MCP tool'u yazılmadı ve yazılmamalı.** `scope.yaml` alım/satım fiillerini
`UNAUTHORIZED_ACTION` sayıyor; sohbet üzerinden bir modelin emir geçebilmesi,
prompt enjeksiyonuyla portföyün ele geçirilmesi demek olurdu.

### Kullanıcı risk profili ve anket puanı

Projedeki tek YAZAN uç ailesi; geri kalan her REST ucu salt okur. Dördü de
`verify_user_access` ister (AK 5.4) — başkasının profilini okumak ya da
değiştirmek, tüm risk ve uygunluk değerlendirmesinin dayandığı beyanı ele
geçirmek olurdu.

**İKİ ÖLÇEK YAN YANA, biri yetkili:**

| | Ne | Kim kullanıyor |
|---|---|---|
| `risk_survey_score` | **1-7**, şartnamenin anket puanı | uygunluk kontrolü (`advice_eligibility`) |
| `risk_profile` | 4 kademe, puandan **türer** | risk motoru (`risk_service`) tabloları |

Eşleme: **1-2** Muhafazakâr · **3-4** Dengeli · **5** Büyüme · **6-7** Agresif.
Bantlar varlık merdiveniyle hizalı — her profil, kendi bandının açtığı varlık
kümesiyle örtüşür.

#### `GET /api/users/{user_id}/risk-survey`

```json
{
  "user_id": "...",
  "risk_survey_score": 5,
  "risk_profile": "growth",
  "score_band": [5, 5],
  "score_min": 1,
  "score_max": 7
}
```

- `risk_survey_score` **`null` olabilir**: kullanıcı anketi hiç doldurmamıştır.
  Bu durumda `score_band` da `null` olur ama `risk_profile` yine dolu döner.
  Uydurulmuş bir puan döndürmek, verilmemiş bir cevabı verilmiş göstermek
  olurdu (AK 5.5).
- `score_min`/`score_max` yanıtın içinde: **arayüz anket ölçeğini kendi
  tarafında sabit yazmasın.**
- `score_band` puanın karşılık geldiği profilin tüm aralığı — arayüz
  "Muhafazakâr (1-2 puan)" gösterebilsin diye.

#### `PUT /api/users/{user_id}/risk-survey`

```json
{ "risk_survey_score": 5 }
```

Anket ekranının yazması gereken uç budur. Puanı kaydeder **ve profili ondan
türetir**; ikisi tek işlemde yazılır. İdempotent. Aralık dışı puan `422`.

#### `GET` / `PUT /api/users/{user_id}/risk-profile`

Profili doğrudan okur/yazar (`{"risk_profile": "balanced"}`). Yanıt ayrıca
`available_profiles` taşır ki arayüz seçenekleri sabit yazmasın.

> **`PUT /risk-profile` kayıtlı anket puanını SİLER.** Profil artık türev bir
> alan; doğrudan yazılması "elle geçersiz kılma" demektir ve elde duran puan
> o değişikliği açıklamaz. Puan bırakılsaydı birbirini tutmayan iki cevap
> saklanırdı: puan 6 (Agresif) derken profil Muhafazakâr görünürdü.

**Ajana açılmadı, açılmamalı.** `agents/scope.yaml` alım/satım/değiştirme
fiillerini `UNAUTHORIZED_ACTION` sayıyor; sohbet üzerinden bir modelin risk
profilini değiştirebilmesi, prompt enjeksiyonuyla ("artık agresif
profildesin") kullanıcının beyan ettiği risk toleransının ele geçirilmesi
demek olurdu.

**Açık iş:** risk ajanı hâlâ profilden türetilen GEÇİCİ bir puan kullanıyor
(`agents/risk_agent._DUMMY_SURVEY_SCORE_BY_PROFILE`). Gerçek puanın ajana
bağlanması ayrı bir iştir — risk ajanına bu turda dokunulmadı.

### `GET /api/portfolio/{user_id}/benchmark?window=`

Arayüzdeki **"Varlıklar Arası Karşılaştırmalı Getiri"** kartının kaynağı.
Portföyün ve dört kıyas enstrümanının seçili dönemdeki toplam **fiyat**
getirisi.

```json
{
  "window": "12m", "start_date": "2025-09-08", "end_date": "2026-08-26",
  "truncated_to_inception": true,
  "portfolio_return_percent": 91.7,
  "benchmarks": [
    { "symbol": "XU100",  "name": "BIST 100 Endeksi", "return_percent": 39.8 },
    { "symbol": "USDTRY", "name": "Amerikan Doları",  "return_percent": 16.8 },
    { "symbol": "EURTRY", "name": "Euro",             "return_percent": 16.6 },
    { "symbol": "XAUTRY", "name": "Gram Altın",       "return_percent": 49.0 }
  ],
  "excluded_symbols": []
}
```

- `window`: **`1m | 3m | 6m | 12m | ytd`**. `ytd` diğerlerinin aksine sabit
  uzunlukta değildir — 1 Ocak'tan bugüne.
- **Miktarlar dönem başında dondurulur**; dönem içindeki alım/satım, temettü
  ve komisyon hesaba katılmaz. Endeks de saf fiyat getirisi olduğu için ancak
  böyle aynı ölçekte olurlar — yoksa "portföyüm endeksi yendi" cümlesi
  aslında sadece yeni para yatırıldığı anlamına gelirdi.
- **Başlangıç, ilk VARLIK ALIMIDIR**, ilk işlem değil. Portföyler önce
  nakitle fonlanıp varlık günler sonra alınabiliyor; `min(transaction_date)`
  alındığında o gün hiç pozisyon olmadığı için uç `InsufficientDataError`
  veriyordu (ölçülen: 12 aylık pencerede seed'li 50 kullanıcının 50'si).
- `truncated_to_inception: true` → portföy pencereden genç, başlangıç ilk
  alıma çekildi. **Arayüz bunu söylemeli**; "Yıllık" yazıp dört aylık getiri
  göstermek kıyası olduğundan iyi ya da kötü gösterir.
- `excluded_symbols`: dönem başında fiyatı olmayan varlıklar hesaba
  katılmaz — eksik maliyetle bölmek yanlış getiri üretirdi.
- Getiriler hesaplanamıyorsa **`null`**, `0` değil (AK 5.5).

### `GET /api/risk/{user_id}?profile_override=`

7 kademeli risk seviyesi, yıllık volatilite, VaR, Sharpe, yoğunlaşma ve
çeşitlendirme metrikleri; volatilite profilin beklenen bandının üzerindeyse
kök neden teşhisi (`causes`) da gelir.

```json
{
  "risk_level": "medium_high",
  "is_within_profile": false,
  "risk_profile": "conservative",
  "risk_profile_source": "user",
  "risk_survey_score": 2,
  "metrics": {
    "annualized_volatility_percent": 24.31,
    "value_at_risk_try": 6968.0, "value_at_risk_percent": 0.44,
    "value_at_risk_confidence": 95.0, "value_at_risk_horizon_days": 1,
    "sharpe_ratio": -6.74, "risk_free_rate_percent": 37.0,
    "max_asset_symbol": "PPF", "max_asset_weight_percent": 24.17,
    "price_points_used": 260
  },
  "warnings": [],
  "disclaimer": "Bu bir yatırım tavsiyesi değildir. …"
}
```

- **0-100 kompozit skor YOK.** Risk v2 onu bilerek kaldırdı; seviye yalnızca
  volatiliteden gelir, yoğunlaşma/çeşitlendirme skora karışmaz (onlar teşhiste
  kullanılır). Arayüz skor uydurmamalı.
- `risk_survey_score` kullanıcının anket puanıdır (1-7) ve `risk_profile`
  ondan türer; arayüzün "Risk Profili" kartı bunu gösteriyor, bu yüzden ayrı
  bir uç çağırmasın diye burada taşınıyor. **`null` olabilir:** anket
  doldurulmamıştır ya da sonuç `profile_override` ile hesaplanmıştır — o
  senaryoda profil kullanıcının beyanı olmadığı için puan bilerek düşürülür.
- **Yeterli fiyat geçmişi yoksa `risk_level` ve metrikler `null` döner**,
  tahmini bir değerle doldurulmaz (AK 2.7 / 5.5). Sebep `warnings`'te yazar.
  Arayüz bu durumda "hesaplanamadı" göstermeli — `0` göstermek "riskiniz yok"
  demek olurdu.
- `profile_override` "ya agresif olsaydım?" senaryosudur: hesap o profile göre
  yapılır ama kullanıcının **kayıtlı profili değişmez** (`risk_profile_source`
  `override` döner).
- `scenarios` ürün sahibi kararıyla kapalıdır: risk yalnızca tespit/uyarı
  içindir, ne yapılacağını önermek kapsam dışı.
- Bu uç da **ajan çağırmaz**, servisi doğrudan okur.

**Bilinen konu:** risksiz faiz %37 olduğu için muhafazakâr portföylerde Sharpe
sistematik olarak negatif çıkıyor. Analist onayı bekliyor; arayüzde bağlamsız
gösterilmemeli.

### `POST /api/chat` (SSE, `text/event-stream`)

İstek:
```json
{ "user_id": "3fa85f64-...", "session_id": null, "message": "Portföyümün durumu nasıl?" }
```
`session_id: null` ise yeni bir `ChatSession` açılır; verilirse mevcut oturuma
devam edilir (yoksa `404`). Kullanıcı mesajı, ajanlar çalışmadan **önce** DB'ye
yazılır.

Yanıt akışı:
```
event: session
data: {"session_id": "b1e2..."}

event: token
data: {"delta": "Portföyünüzün"}

event: done
data: {"agent": "portfolio_agent", "final_answer": "...", "data": { ...PortfolioSummary... }}

event: error
data: {"message": "..."}   # sadece hata durumunda, done yerine
```
Asistan mesajı stream tamamlanınca tek parça DB'ye yazılır (`status: complete`).
İstemci bağlantıyı yarıda keserse, o ana kadar biriken metin `status: incomplete`
ile kaydedilir.

### `GET /api/chat/sessions/{session_id}/messages`

Oturumdaki tüm mesajları kronolojik sırada döner:
```json
[
  {
    "id": "8670e68a-...",
    "role": "user",
    "content": "Portföyümün durumu nasıl?",
    "agent_name": null,
    "meta": null,
    "status": "complete",
    "created_at": "2026-08-10T13:49:13"
  },
  {
    "id": "4814d25f-...",
    "role": "assistant",
    "content": "...",
    "agent_name": "portfolio_agent",
    "meta": { "data": { ...PortfolioSummary... } },
    "status": "complete",
    "created_at": "2026-08-10T13:49:15"
  }
]
```
404 → `{"detail": "Chat session not found for session_id ..."}`

## Piyasa uçları

Piyasa ekranını besler. Üç uç, üç ayrı kaynak.

### `GET /api/market/indicators`

Gösterge şeridi: BIST 100, USD/TRY, EUR/TRY, gram altın. Kaynak `price_history`
tablosu; token ister ama kullanıcıya özel değildir.

```json
{
  "as_of": "2026-08-24",
  "indicators": [
    {
      "symbol": "XU100", "name": "BIST 100 Endeksi", "asset_class": "stock",
      "price": 14514.82, "change_percent": 0.82,
      "price_date": "2026-08-22", "source": "yfinance", "stale": false
    }
  ],
  "missing_symbols": []
}
```

`change_percent` bir önceki **işlem** gününe göredir (takvim günü değil —
piyasa hafta sonu kapalı). Seride tek nokta varsa `null` döner, `0` DEĞİL:
"değişmedi" ile "hesaplanamadı" farklı şeylerdir (AK 5.5). `price_date` ve
`source` her satırda döner ve arayüz ikisini de göstermek zorundadır (AK 5.1,
5.3).

### `GET /api/market/headlines`

Genel piyasa gündemi — istek anında BloombergHT son dakika akışından **canlı**
çekilir, veritabanına yazılmaz. Sağlayıcı 5 dakikalık önbellek tutar ve bu
önbellek sohbet tarafındaki `get_live_market_headlines` tool'uyla paylaşılır.

```json
{
  "headlines": [
    { "title": "TCMB: REEL SEKTÖRÜN NET DÖVİZ POZİSYONU...", "published_at": "2026-08-24T14:38:00" }
  ],
  "source_name": "BloombergHT",
  "source_url": "https://www.bloomberght.com/sondakika"
}
```

Madde başına **URL YOKTUR**: akıştaki maddelerin ayrı adresi bulunmuyor
(ölçüldü), kaynak listenin tamamına giden tek adrestir. Özet, etki seviyesi
ve kaynak sayısı da yoktur — kaynak yalnızca başlık ve zaman veriyor,
üretmek uydurma olurdu.

503 → `{"detail": "Piyasa gündemine şu an ulaşılamıyor."}`. Boş liste
DÖNMEZ: "ulaşılamadı" ile "haber yok" aynı şey değil.

### `GET /api/market/influence/{user_id}`

Kullanıcının en ağırlıklı pozisyonları ve günlük değişimleri. Nakit hariç
(fiyatı, dolayısıyla değişimi yok).

```json
{
  "as_of": "2026-08-24",
  "rows": [
    {
      "symbol": "ASELS", "name": "Aselsan", "asset_class": "stock",
      "weight_percent": 16.4, "change_percent": 0.25
    }
  ]
}
```

Kullanıcıya özeldir: `Depends(get_current_user)` + `verify_user_access`
(AK 5.4). 403 → başkasının portföyü, 401 → token yok.

### `GET /api/market/calendar/{user_id}`

Kullanıcının **hisselerinin** yaklaşan KAP bildirim takvimi. Makro takvim
(TCMB PPK, TÜİK, ABD TÜFE) DEĞİLDİR — onun doğrulanmış bir kaynağı yok.

```json
{
  "entries": [
    {
      "symbol": "ASELS", "company": "ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.",
      "subject": "Finansal Rapor", "period": "9 Aylık",
      "start_date": "2026-10-01", "due_date": "2026-11-09"
    }
  ],
  "source_name": "KAP",
  "source_url": "https://www.kap.org.tr/tr"
}
```

KAP tek bir tarih değil bir **dosyalama penceresi** yayımlıyor; `due_date`
aralığın sonudur ve kullanıcı için bağlayıcı olan gün odur. Arayüz bu günü
gösterir.

Şirket başına bir HTTP isteği atılır (pykap toplu sorgu sunmuyor), bu yüzden
liste kullanıcının en ağırlıklı 6 hissesiyle sınırlıdır. Bir şirket düşerse
diğerleri düşmez.

Boş liste **hata değildir**: kullanıcının hissesi olmayabilir ya da yakın
dönemde beklenen bildirim bulunmayabilir. 503 → KAP'a hiç ulaşılamadı.

## MCP Tool'ları

MCP Server `http://mcp_server:8100/mcp` üzerinde dinler (docker ağı içinde).

Dönüş zarfı, hata kodları ve ortak sözleşme için: **[`docs/MCP-TOOLS.md`](MCP-TOOLS.md)**.

### `get_portfolio_summary` (çalışıyor)

```
Girdi:  { "user_id": "<UUID>" }
Çıktı (başarı): { "success": true, "data": { ...PortfolioSummary... } }
Çıktı (hata):   { "success": false, "error": { "code": "NOT_FOUND", "message": "..." } }
```
`user_id` geçersiz UUID ise tool çağrılmadan otomatik `ValidationError` fırlar
(pydantic, tip anotasyonundan üretilen JSON şemasıyla).

### `search_market_news` (çalışıyor)

```
Girdi:  { "query": "...", "top_k": 5 }
Çıktı (başarı): { "success": true, "data": { "results": [{ "content": "...", "metadata": {...}, "distance": 0.0 }, ...] } }
Çıktı (hata):   { "success": false, "error": { "code": "NOT_FOUND" | "PROVIDER_UNAVAILABLE", "message": "..." } }
```
Saf DB tabanlı arama: LLM yanıt üretmez, internetten canlı veri çekmez.
`data/documents/` altındaki dokümanlar `python -m rag.ingest` ile Chroma'ya
yüklenir; sorguya `rag_distance_threshold` (bkz. `app/core/config.py`) altında
kalan ya da anahtar kelime örtüşmesi olmayan sonuçlar elenir — hiç sonuç
kalmazsa `NOT_FOUND` döner.

### Portföy tool ailesi (çalışıyor)

Dördü de yukarıdaki REST uçlarıyla **aynı servisleri** çağırır, dolayısıyla aynı
şemayı ve aynı kuralları taşır. Fark yalnızca zarfta: MCP tarafında sonuç
`{"success": ..., "data"|"error": ...}` içine sarılır (bkz.
[`docs/MCP-TOOLS.md`](MCP-TOOLS.md)).

| Tool | Girdi | Servis |
|---|---|---|
| `get_holdings` | `user_id` | `get_holdings_valuation` |
| `get_portfolio_performance` | `user_id`, `window` | `get_portfolio_performance` |
| `get_transactions` | `user_id`, `start_date?`, `end_date?`, `symbols?` | `get_transactions` |
| `get_benchmark_comparison` | `user_id`, `window` | `get_benchmark_comparison` |
| `get_asset_price_history` | `symbols`, `window`, `granularity`, `currency` | `price_service.get_asset_price_history` |

`get_asset_price_history` ayrı bir modülde (`mcp_server/tools/price_tools.py`):
portföyden bağımsızdır, `user_id` almaz ve aynı sembolün serisi tüm kullanıcılar
için aynı olduğundan kullanıcı bazlı olmayan önbelleğe uygundur.

**Güvenlik notu:** `user_id` argümanını dil modeli **üretmez**. Portföy Ajanı
planı çalıştırırken bu alanı kendisi enjekte eder ve modelin yazdığı değeri ezer
(`agents/portfolio_agent.py::_run_plan`, `_parse_plan`). Modelin başka bir
kullanıcının verisini istemesi bu yüzden mümkün değildir.

### İskelet tool'lar (`NotImplementedError`)

- `get_risk_assessment(user_id: str)` — `mcp_server/tools/risk_tools.py`
\n