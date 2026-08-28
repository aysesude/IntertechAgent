# Sinyal 5 (profil_sapmasi) — Olay Tabanlı Aktivasyon: Tasarım Planı

**Tarih:** 2026-08-27
**Durum:** Taslak — kod yazılmadı, analiste/ekibe onay için hazırlandı.
**İlgili dosyalar (mevcut, incelendi):** `agents/risk_agent.py`, `agents/prompts/risk_signals.md`,
`backend/app/models/user.py`, `backend/app/services/user_service.py`,
`backend/app/services/advice_eligibility.py`, `mcp_server/tools/risk_tools.py`, `agents/base.py`,
`agents/orchestrator.py`, `backend/alembic/versions/f18c4a2e7b90_user_risk_survey_score.py`,
`tests/test_risk_survey_score.py`

---

## 1. Özet

2026-08-26'da analistle netleşen karar: Sinyal 5, ağırlığa/yüzdeye bakmayan, yalnızca kullanıcının
anketi **yeniden doldurduğu ANDA** tetiklenmesi gereken bir sinyal olmalı. O tarihte bu event'i
yakalayacak bir mekanizma yoktu, sinyal kalıcı dormant yapıldı.

Aynı gün paralelde bir takım arkadaşı gerçek bir anket-puanı sistemi eklemiş
(`users.risk_survey_score`, `set_user_risk_survey()`, `PUT /api/users/{id}/risk-survey`). Bu,
Sinyal 5'in beklediği "gerçek anket sonucu" var oluşunu sağlıyor — **ama tek başına yeterli değil**,
çünkü sistemde şu an sadece kullanıcının *mevcut* anket puanı tutuluyor, anketin *ne zaman* dolduğu
tutulmuyor. "Mevcut puana bak" statik bir durumdur, olay değildir; bunu tetikleyici olarak
kullanmak, analistin özellikle reddettiği pasif kontrolün (eski `_dummy_survey_score` yaklaşımı)
gerçek verilerle yeniden kurulması olurdu.

Bu belge, gerçek bir olay (anket az önce yeniden dolduruldu, henüz kimseye gösterilmedi) ile
gerçek bir ihlal kontrolünü (yeni profilin izin vermediği bir sınıf hâlâ elde mi) birleştiren bir
tasarım öneriyor.

## 2. Tetikleme mantığı

Sinyal 5, **ikisi birlikte** sağlandığında ve YALNIZCA o zaman devreye girer:

1. **Olay:** Kullanıcının `risk_survey_score`'u en son ne zaman güncellendiyse, bu güncelleme henüz
   hiçbir risk değerlendirmesine "tüketilmemiş" — yani kullanıcı anketi yeniden doldurdu ve bu
   henüz kendisine hiç yansıtılmadı.
2. **İhlal:** Yeni puanın izin verdiği varlık sınıfları (`advice_eligibility.allowed_asset_classes`)
   ile kullanıcının GÜNCEL elindeki varlık sınıfları karşılaştırıldığında, artık izin verilmeyen
   en az bir sınıf elde kalmış.

İkisi birden olmadan sinyal hiç üretilmez; context'e ilgili alanlar hiç eklenmez (mevcut davranışla
aynı prensip: "üretilemiyorsa hiç bahsetme").

Önemli: "izin verilmeyen sınıf elde mi" karşılaştırması **deterministik Python kodunda**
hesaplanıp LLM'e hazır liste olarak veriliyor — LLM'den "ağırlığa bakarak karar ver" istenmiyor,
sadece elindeki listeyi anlatması isteniyor. Ağırlık/yüzde hâlâ bu sinyalin karar mekanizmasına
hiç girmiyor.

## 3. Dosya dosya değişiklik planı

### 3.1 Migration (yeni, `f18c4a2e7b90`'ın üzerine)
`users` tablosuna iki nullable `DateTime(timezone=True)` kolonu:

- `risk_survey_updated_at` — anket puanı en son ne zaman yazıldı.
- `risk_survey_event_consumed_at` — bu güncelleme en son ne zaman bir risk değerlendirmesine
  yansıtıldı (tüketildi).

"Bekleyen olay var" tanımı: `risk_survey_updated_at IS NOT NULL AND (risk_survey_event_consumed_at
IS NULL OR risk_survey_event_consumed_at < risk_survey_updated_at)`. İki ayrı zaman damgası
kullanmak (tek bir boolean yerine) hem "ne zaman oldu" hem "ne zaman görüldü" bilgisini kaybetmeden
taşıyor.

### 3.2 Model — `backend/app/models/user.py`
Yukarıdaki iki `Mapped[datetime | None]` kolonu, mevcut `risk_survey_score` bloğunun yanına aynı
gerekçe-yorumu üslubuyla eklenir.

### 3.3 Service — `backend/app/services/user_service.py`
`set_user_risk_survey()` içine `user.risk_survey_updated_at = datetime.now(UTC)` satırı eklenir
(puan/profil yazımıyla AYNI transaction'da). `consumed_at`'e bu fonksiyon hiç dokunmaz — yeni bir
anket sonucu her zaman "tüketilmemiş" başlar.

`set_user_risk_profile()` (doğrudan/elle profil değiştirme yolu) **değişmez** — o yol zaten
`risk_survey_score`'u `None`'a düşürüyor; elle yapılan bir değişiklik hiçbir zaman "anket olayı"
sayılmamalı.

### 3.4 Yeni MCP tool — `mcp_server/tools/risk_tools.py` içine `get_risk_survey_event`
Tek işi: bekleyen olayı okumak VE varsa aynı anda tüketilmiş işaretlemek (atomik "oku ve tüket").

**Kritik tasarım kararı:** tüketme kararını LLM/ajan vermez — bu, deterministik Python kodunun
kendi kararıdır. `agents/base.py`'nin ilkesiyle uyumlu ("Ajanlar veriye asla doğrudan erişmez") ve
`scope.yaml`'ın "ajan kullanıcının risk verisini asla değiştiremez" kuralıyla çelişmez — çünkü bu
yan etki `risk_profile`/`risk_survey_score`'un kendisine dokunmuyor, yalnızca bir "bildirim
gösterildi" bayrağı.

Dönen veri:
- Bekleyen olay yoksa: `{"olay_var": false}`.
- Varsa: `{"olay_var": true, "yeni_profil": "...", "izin_verilmeyen_ve_elde_olan_siniflar": [...]}`
  — son alan `allowed_asset_classes(risk_survey_score)` ile güncel holdings'in farkı olarak
  serviste hesaplanır.

### 3.5 `agents/risk_agent.py`
`_assess_signals` içine, mevcut `get_holdings`/`get_portfolio_news` çağrılarının yanına üçüncü bir
`call_mcp_tool("get_risk_survey_event", ...)` eklenir. Tool başarısız olursa ya da `olay_var:
false` dönerse mevcut davranış aynen sürer. `olay_var: true` VE liste boş değilse
`_build_signal_context`'e yeni bir parametre eklenir, context'e SADECE bu durumda
`anket_yeniden_dolduruldu` ve `yeni_profille_izinsiz_kalan_siniflar` alanları yazılır.

Modül docstring'i üçüncü kez güncellenir ("2026-08-27 eki") — önceki iki kararın izini
silmeden, üstüne eklenerek.

### 3.6 Prompt — `agents/prompts/risk_signals.md`
Madde 5 ve ilgili ZORUNLU KURAL satırı: "hiç kullanma" yerine "yalnızca
`anket_yeniden_dolduruldu` ve dolu bir `yeni_profille_izinsiz_kalan_siniflar` verildiyse, ve
YALNIZCA o listedeki sınıflar için tetikle" şeklinde koşullu hale getirilir. Ağırlığa bakmama
kuralı aynen kalır.

### 3.7 Testler
- `tests/test_risk_survey_score.py`: `set_user_risk_survey` sonrası `risk_survey_updated_at`'in
  dolduğunu, `set_user_risk_profile`'ın ona dokunmadığını doğrulayan testler.
- Yeni testler (risk_tools için): olay yok / olay var+ihlal yok / olay var+ihlal var, ve tool ikinci
  kez çağrıldığında `olay_var: false` dönmesi (gerçekten tüketildiğinin kanıtı).
- `tests/test_risk_agent.py`: üçüncü tool çağrısının yapıldığı, context alanlarının SADECE doğru
  koşulda eklendiği. Mevcut `test_sinyal_baglami_anket_alanlari_hicbir_zaman_eklenmez` testi
  isim/içerik olarak güncellenmeli — artık "hiçbir zaman" değil "yalnızca olay varsa".

## 4. Analiste/ekibe götürülmesi gereken açık sorular

Bunlar benim tek başıma karar vereceğim noktalar değil:

1. **Ne zaman "tüketilsin"?** Şu anki öneri: `_assess_signals` çağrıldığı an (kullanıcı "ne
   yapmalıyım" tipi bir soru sorduğunda) — basit ama LLM o turda sinyali JSON'a koymayı
   atlarsa/hata verirse olay bir daha hiç görünmez. Alternatif: yalnızca `RiskSignalAssessment`
   BAŞARIYLA üretildiğinde tüket (daha güvenli, tool iki adımlı olur: "oku" + ayrı "tüket").
2. **Anket art arda birkaç kez değiştirilirse** (deneme-yanılma), her biri ayrı olay mı, yoksa
   sadece en son mu sayılsın? Şu anki tasarım otomatik "en son" diyor (tek `updated_at`, üzerine
   yazılıyor) — aradakiler hiç görülmez.
3. **"İzin verilmeyen ve elde olan sınıflar" hangi holdings anına göre hesaplanır** — tam sorgu
   anına göre mi (öneri budur), yoksa anketin dolduğu ana en yakın olana göre mi?

## 5. Kapsam dışı — dokunulmuyor

- `RiskProfile` enum'u (4 kademe) — hâlâ bloke, bu tasarım onu değiştirmiyor.
- MEVDUAT-V / AK 5.1 kararı — ilgisiz.
- `set_user_risk_profile` (elle profil değiştirme) davranışı — değişmiyor.
