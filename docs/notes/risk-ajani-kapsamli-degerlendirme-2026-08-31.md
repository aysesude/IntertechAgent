# Risk ajanı: "risk seviyem nedir" sorusu artık portföyün tamamını anlatıyor

**Tarih:** 2026-08-31 · **Karar:** Yağız · **Branch:**
`risk-agent-sinyal-gorunur-yagiz` (`test`'ten açıldı)

## Sorun

Test ortamında "Portföyüm ne kadar riskli?" ve "portföyümün risk seviyesi
nedir" sorularına gelen cevap yalnızca volatilite özetiydi: risk seviyesi,
profil bandı, en büyük varlık sınıfı. Portföyün %86'sı nakit olmasına rağmen
yoğunlaşmadan söz edilmiyor, elde profil dışı varlık olup olmadığı
söylenmiyor, haberler hiç yorumlanmıyordu.

İstenen davranış (Yağız): bu tip sorularda ajan portföyü alsın, yoğunlaşmaya
baksın, varlıkların anket puanına uyup uymadığını kontrol etsin (kullanıcı
anketi yeniden çözmüş ve puanı düşmüş olabilir), profilin üstünde varlık
varsa bunu bildirsin, ve elindeki varlıklarla ilgili haberleri yorumlasın.

## Bulgu: iş zaten yazılmıştı, görünmüyordu

Denetimde çıkan sonuç: istenen davranışın neredeyse tamamı kodda vardı.
`_assess_signals` beş sinyali (`konsantrasyon`, `sektor_yogunlasmasi`,
`olumsuz_haber`, `sektor_gelismesi`, `profil_sapmasi`) üretiyor,
`get_holdings` + `get_portfolio_news` + `get_macro_news` çağırıyordu.
`advice_eligibility.mismatched_asset_classes` de hazırdı.

Üç tıkanma vardı:

1. **`_assess_signals` soru filtresinin arkasındaydı.** `_wants_scenarios`
   yalnızca soruda `dengele/azalt/oneri/strateji/iyilestir/ne yapmali`
   köklerinden biri geçerse `True` dönüyor. "Risk seviyesi nedir" bunların
   hiçbirini içermiyor → sinyal değerlendirmesi hiç çalışmıyordu.
2. **Çalıştığında bile çıktısı atılıyordu.** Sonuç yalnızca
   `response_data["risk_signal_assessment"]`'a yazılıyordu. Bu alanı repoda
   **hiçbir yer okumuyor**, ve `orchestrator.merge_responses` yalnızca
   `summary_text`'i topluyor.
3. **Yoğunlaşma teşhisi yalnızca bant aşılınca hesaplanıyordu.**
   `risk_service`'te `causes = _diagnose_causes(...)` çağrısı
   `if not is_within_profile:` içindeydi. Prompt kuralı 7 de motor tespit
   etmeden yoğunlaşmadan söz etmeyi (haklı olarak) yasakladığı için, bandın
   içindeki hiçbir portföyde yoğunlaşma görünemiyordu.

## Yapılanlar

**Yeni MCP tool'u eklenmedi.** İhtiyaç duyulan her şey (holdings, haberler,
anket puanı, varlık risk seviyeleri) mevcut tool'larda zaten vardı; iş
bağlamaktı.

| Dosya | Değişiklik |
|---|---|
| `advice_eligibility.py` | Yeni `mismatched_holdings()` — sınıf düzeyi sürümün VARLIK düzeyi karşılığı. Mevcut fonksiyonlara dokunulmadı. |
| `schemas/risk.py` | Yeni `MismatchedHolding` modeli; `RiskAssessment.mismatched_holdings` alanı; `causes` yorumu güncellendi. |
| `risk_service.py` | Uyumsuzluk hesabı (portföy + puan zaten yüklü, ek sorgu yok); `_diagnose_causes` artık her durumda çağrılıyor. |
| `risk_agent.py` | `_compact` uyumsuzluğu taşıyor; yeni `_sinyal_blogu`; `_assess_signals` her risk sorusunda çalışıyor ve metne giriyor. |
| `prompts/risk_agent.md` | Yeni kural 10 (uyumsuzluk bildirimi); kural 7 genişletildi (bant içinde yoğunlaşma nötr tonda anlatılır). |

### Uyumsuzluk neden VARLIK düzeyinde

Puanı 5 olan kullanıcının elindeki BHE (serbest fon) sınıf karşılaştırmasıyla
(`STOCK=5 <= 5`) **uyumlu** görünür; varlığın kendi uygunluk seviyesi 7
olduğu için aslında uyumsuzdur. `advice_eligibility` modülü zaten "bir
varlığın uygunluğuna karar verirken sınıf fonksiyonları DEĞİL, varlık düzeyi
kullanılmalıdır" diyor.

### Sinyal bloğunda ne gösteriliyor, ne gösterilmiyor (onaylandı, Yağız)

Yalnızca `risky_assets` (varlık bazlı bulgular) gösteriliyor. Dışarıda
bırakılanlar ve gerekçeleri:

- **`risk_level`** — LLM'in kendi kategorik yargısı ("orta_riskli"), ana
  yanıttaki deterministik seviyeden (volatiliteden gelen "Çok Düşük")
  bağımsız üretiliyor. İkisini aynı mesajda göstermek kullanıcıya **çelişen
  iki risk seviyesi** sunmak olurdu — `_compact`'teki
  `profil_bandinda_mi`/`profil_konumu` çelişkisinin aynısı.
- **`rebalancing`, `investment_strategy`** — Ürün Sahibi kararıyla (2026-08,
  `Settings.risk_scenarios_enabled`) "ne yapılmalı" önerisi ürün kapsamı
  dışında; risk artık yalnızca tespit/bildirim.
- **`profile_fit`** — uyumsuzluk artık deterministik olarak ana yanıtta
  anlatılıyor; LLM'in ikinci bir yorumu aynı şeyi iki kez, muhtemelen farklı
  söylerdi.

Blok kod tarafında birleştiriliyor, üçüncü bir LLM çağrısı yok.

## 2026-08-26 analist kararıyla ilişkisi

O karar ("sinyal 5 ağırlıklara bakmasın, sadece anket yeniden doldurulunca
tetiklensin") **aynen geçerli ve bu işte hiç değiştirilmedi.** Sinyal 5'in
Yol A/Yol B mantığına dokunulmadı.

Eklenen deterministik uyumsuzluk yolu bir OLAYA değil MEVCUT DURUMA bakıyor
(`elde tutulan varlıklar` × `güncel anket puanı`), dolayısıyla olay
mekanizmasından bağımsız. Reddedilmiş olan şey "Sinyal 5'in her turda pasifçe
tetiklenmesi"ydi; burada tetiklenen Sinyal 5 değil, ayrı bir bildirim yolu.

## Kabul edilen bedeller ve bilinen yan etki

- **Maliyet:** her risk sorusunda ek `get_holdings` + `get_portfolio_news` +
  `get_macro_news` çağrısı ve bir ek LLM turu. Yanıt yavaşlayacak. Bilinerek
  kabul edildi.
- **Anket olayı daha erken tüketiliyor:** `get_risk_survey_event` "oku ve
  tüket" mantığıyla çalışıyor ve artık her risk sorusunda çağrılıyor. Sinyal
  5 Yol A bulgusu artık metne girdiği için tüketim ile gösterim aynı turda
  oluyor; yine de LLM o bulguyu üretmezse olay görünmeden harcanır. Bu risk,
  deterministik uyumsuzluk yolu sayesinde kullanıcı açısından telafi ediliyor
  — uyumsuzluk bilgisi olaydan bağımsız olarak her zaman veriliyor.
- **Bir test beklentisi tersine çevrildi:**
  `test_get_risk_assessment_asset_metrics_populated_when_within_profile`
  içindeki `assert assessment.causes is None`, eski davranışı kilitliyordu;
  artık `is not None`. Testin asıl amacı (bant içinde `asset_metrics` boş
  kalmamalı) değişmedi.

## Doğrulama

- Hedefli: `pytest /tests/test_risk_service.py /tests/test_risk_agent.py -q`
  → **60 passed**
- Tam suite: `pytest /tests -q` → **764 passed**
- Yeni testler: `test_risk_service.py`'de 6 (uyumsuzluk bant içinde bildirilir,
  varlık düzeyinde hesaplanır, eşit seviye girmez, anket puanı yoksa boş,
  override'da boş, bant içinde yoğunlaşma teşhisi), `test_risk_agent.py`'de 6
  (compact'e uyumsuzluk + puan taşınır, boşsa hiç eklenmez, sinyal bloğu
  bulguları çevirir, çelişen ikinci seviyeyi göstermez, bulgu yoksa boş,
  düşük güvende kapsam uyarısı).

## Açık kalanlar

- **Frontend tipleri.** `schemas/risk.py` docstring'i "frontend'deki
  `src/types/` altındaki TypeScript tipleri bu şemayla eşleşmelidir" diyor.
  `mismatched_holdings` alanı eklendi; TS tarafına yansıtılması ayrı bir iş
  (alan eklemek geriye dönük uyumlu olduğu için acil değil).
- **Merge adımı bazı uyarıları düşürebiliyor.** `merge_responses`'ın
  "elenemez" listesinde sinyal bloğu yok; ikinci LLM turu onu kısaltabilir
  ya da düşürebilir. Aynı sınırlama web_research için de kayıtlı (bkz.
  `analiste-kapsam-sapmalari.md` → "Ek — iş kalemi"). Bu iş de oraya bağlı.
