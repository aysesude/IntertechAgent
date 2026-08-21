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
