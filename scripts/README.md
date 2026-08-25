# scripts/ — geliştirme doğrulama araçları

Bunlar **test değildir**; `pytest` bunları toplamaz ve CI çalıştırmaz. Hepsi
gerçek veritabanına, gerçek MCP sunucusuna veya gerçek LLM sağlayıcısına ihtiyaç
duyduğu için otomatik teste giremiyor — elle, ihtiyaç anında çalıştırılır.

Hepsi konteynerden çalışır (`./scripts` `api` servisine mount edilir):

```bash
docker compose exec -w / api python scripts/<betik>.py [argümanlar]
```

Kullanıcı UUID'si için:

```bash
docker compose exec postgres psql -U finans -d finans_danismani \
  -c "SELECT id, email FROM users LIMIT 5;"
```

## `llm_smoke.py`

**Ne zaman:** `.env` ilk kez doldurulduğunda, sağlayıcı değiştiğinde ya da
sohbet boş/hatalı cevap verdiğinde.

`generate()` ve `stream()` çağrılarını ayrı ayrı dener, ağ geçidinin ham SSE
yanıtını gösterir. API anahtarını maskeler, asla yazdırmaz.

```bash
docker compose exec -w / api python scripts/llm_smoke.py
```

## `plan_smoke.py <user_id>`

**Ne zaman:** `agents/prompts/portfolio_agent.md` ya da tool docstring'leri
değiştiğinde.

Beş soru sorup Portföy Ajanı'nın her biri için hangi tool'u seçtiğini ölçer.
Planlama gerçek LLM ile yapıldığı için pytest'e giremiyor. Tool'un stub olması
plan başarısını etkilemez — bakılan alan `selected_tools`.

```bash
docker compose exec -w / api python scripts/plan_smoke.py <user_id>
```

## `capraz_kontrol.py <user_id>`

**Ne zaman:** portföy matematiğine dokunulduğunda.

Varlık değerlerini, maliyetleri, ağırlıkları, K/Z yüzdelerini ve pozisyonları
**ham SQL ile** yeniden hesaplayıp servis katmanının çıktısıyla karşılaştırır.
Testleri de servisi de aynı kişi yazdıysa ortak bir yanlış varsayım ikisinde
birden yaşar; bu betik bağımsız ikinci bir yöntem sunar. Uyuşmazlık varsa çıkış
kodu 1.

```bash
docker compose exec -w / api python scripts/capraz_kontrol.py <user_id>
```

## `varlik_risk_olcum.py`

**Ne zaman:** varlık bazlı risk etiketine ya da
`RISK_LEVEL_VOLATILITY_UPPER_BOUNDS` tablosuna dokunulmadan önce.

Evrendeki her varlığın gerçek yıllık volatilitesini üretimdeki hesabın
aynısıyla (`_returns_aligned` + `_annualized_volatility`, TRY'ye çevrilmiş
seri üzerinden) ölçer ve mevcut 7 kademeli eşik tablosunun varlık düzeyinde
nasıl dağıldığını gösterir.

Sorduğu soru: eşikler portföy volatilitesine göre kalibre edilmişti; tek bir
varlığa uygulandığında kademeler anlamlı ayrışıyor mu, yoksa hepsi en üst
basamaklarda yığılıyor mu? Karşılaştırma için ölçülen dağılımı yedi eşit
dilime bölen alternatif bir merdiven de basar — otomatik uygulanmaz, yalnızca
karara girdidir.

Hiçbir şey yazmaz, salt okur.

```bash
docker compose exec -w / api python scripts/varlik_risk_olcum.py
docker compose exec -w / api python scripts/varlik_risk_olcum.py --gun 252
```

## `fiyat_sicrama_teshis.py`

**Ne zaman:** `varlik_risk_olcum.py` gerçekçi olmayan (örn. binlerce yüzde)
bir volatilite değeri gösterdiğinde — eşik tasarımına geçmeden önce bunun
piyasa hareketi mi yoksa veri hatası mı olduğunu ayırt etmek için.

İki ayrı hipotezi doğrudan veriden doğrular/eler: (1) DB'deki
`Asset.asset_class`, `providers/universe.py`'deki güncel tanımla aynı mı —
farklıysa `data.generate_dummy` bu sınıf değişikliğinden sonra hiç
çalışmamış demektir; (2) fiyat serisinde `seed_prices_synthetic.py`'nin
belgelediği türden sahte bir tek-günlük sıçrama (sentetik/gerçek taban
fiyat uyuşmazlığı) var mı.

Hiçbir şey yazmaz, salt okur.

```bash
docker compose exec -w / api python scripts/fiyat_sicrama_teshis.py
docker compose exec -w / api python scripts/fiyat_sicrama_teshis.py --sembol PPF,GTA
```

## `data_doctor.py`

**Ne zaman:** portföy rakamları tuhaf göründüğünde — abartılı kâr/zarar, bir
varlıkta olmayacak bir yüzde, ya da bir migration/backfill sonrası "acaba veri
tutarlı mı" şüphesi. Sunum öncesi tek seferlik sağlık kontrolü olarak da
çalıştırılabilir.

Tek bir soruyu cevaplar: **maliyet ile değerleme aynı evrenden mi geliyor?**

`seed_ledger` her işlemi, işlemin yapıldığı GÜNÜN `price_history` kaydından
fiyatlar — bu doğrudur ama tek yönlü korur. `make backfill` `make seed`'den
SONRA çalıştırılırsa gerçek fiyatlar, defterin dayandığı sentetik satırların
üzerine yazılır: maliyet artık var olmayan bir fiyattan görünür, değerleme
gerçek fiyattan yapılır. `docs/DATA.md` doğru sırayı (önce backfill, sonra
seed) yazar ama hiçbir şey bunu zorlamaz. 20 Ağustos 2026'da ölçülen sonuç:
151 işlem, 50 portföyün 48'i bozuk, bir varlıkta +%292 sahte kâr.

Altı kontrol: fiyat kaynağı dağılımı · gerçek serinin içinde kalan sentetik
satır · **işlem fiyatı ↔ o tarihteki `price_history`** (belirleyici olan) ·
defter/fiyat tarih aralıkları · şüpheli günlük sıçramalar · aşırı pozisyon K/Z.

`fiyat_sicrama_teshis.py` ile ilişkisi: o betik tek bir varlığın sıçramasını
ve sınıf etiketini teşhis eder (dar ve derin); bu betik tüm defterin maliyet
tutarlılığını ölçer (geniş). Sıçrama kontrolü ikisinde de var — bu betik
"bir sorun var mı" der, diğeri "hangi varlıkta, neden" der.

Çözüm önerisi **koşulludur**: sıra hatası bulunduğunda yeniden seed önerir.
Yalnızca ANCHOR_DATE açığı bulunduğunda önermez — defter `settings.anchor_date`'e
sabitli olduğu için yeniden seed o açığı kapatmaz, yanlış tavsiye olurdu.

Hiçbir şey yazmaz, salt okur. Çıkış kodu: 0 temiz, 1 bulgu var.

```bash
make data-doctor
docker compose exec -w / api python -m scripts.data_doctor
```

**Canlı ortamda (`/opt/finans/prod`)** kaynak kodu bind mount edilmez ve imaj
yalnızca `backend/`'den kurulur, yani konteynerde `/scripts` YOKTUR. Orada
betiği stdin'den geçirin — dosyanın konteynerde bulunmasına gerek kalmaz:

```bash
sudo docker compose -p finans-prod exec -T -w / api python - < scripts/data_doctor.py
```
