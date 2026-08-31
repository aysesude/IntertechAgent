# Sinyal 5 (profil_sapmasi) — Aktivasyon Tasarımı (İki Yol)

**Tarih:** 2026-08-27, **2026-08-28'de genişletildi**
**Durum:** Yol A VE Yol B'nin kod tarafı yazıldı, doğrulandı (ast/black/ruff
+ tam pytest suite, 696 passed) ve teslim edildi (2026-08-28). Analist
sorusu (§5 madde 4) cevaplandı: "risk seviyesi yüksek çıktı ama daha az
riskli varlıkları var" → (a) `advice_eligibility`. Yol A'nın kendi 3 açık
sorusu (§5 madde 1-3) hâlâ cevap bekliyor, ama kod BASİT/varsayılan
yorumla ilerletildi (bkz. ilgili maddeler).

**2026-08-28 eki — kapsam genişledi.** Analist netleşti: Sinyal 5 tek değil, **iki ayrı yoldan**
tetiklenmeli — "yeniden doldurulduğunda VE risk kapasitesi kullanılmadığında". Bu, 2026-08-26'daki
"yalnızca anket yenileme" kararını (bkz. `agents/risk_agent.py` modül docstring'i) daraltmıyor,
**genişletiyor**: o karar hâlâ geçerli (Yol A), yanına ikinci, bağımsız bir tetikleyici ekleniyor
(Yol B). İkisinin veri ihtiyacı ve karmaşıklığı çok farklı — plan aşağıda ayrı ayrı ele alıyor.
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

## 2. Yol A — Olay tabanlı (anket yenilendi + izinsiz sınıf elde kaldı)

Bu YOL, **ikisi birlikte** sağlandığında ve YALNIZCA o zaman devreye girer:

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

## 3. Yol B — Kapasite kullanılmaması (YENİ, 2026-08-28)

"riskk" dokümanının Sinyal 5 alt durumu: *"Portföy tamamen düşük riskli sınıflarda kalmış ve profil
daha fazlasına izin veriyorsa, bu da bir sapmadır."* Bulgu **bilgilendirme tonunda** olmalı, uyarı
değil (dokümanın kendi ifadesiyle: "Portföyünüz risk profilinizin öngördüğünden daha temkinli bir
yapıda").

**Yol A'dan temel farkı:** hiçbir OLAYA ihtiyaç duymuyor. Şu an elde olan holdings + şu an geçerli
`risk_survey_score` yeterli — `risk_survey_updated_at`/`risk_survey_event_consumed_at` (bkz. §4'ün
Yol A kısmı) gerekmiyor. Yani bu yol, Yol A'nın altyapısını (migration, yeni MCP tool) beklemeden
BUGÜN uygulanabilir.

**Çözülmesi gereken tek belirsizlik — hangi "kapasite"?** Kod tabanında birbirine benzeyen ama FARKLI
iki "profile göre az risk almak" kavramı var:

- **(a) Uygunluk sınıfı kullanılmaması** (`advice_eligibility.allowed_asset_classes`) — puan daha
  yüksek sınıflara (ör. hisseye) izin veriyor ama kullanıcının elinde o sınıftan hiç yok. İkili
  (izinli/izinli değil), ağırlık taşımıyor.
- **(b) Kategori ağırlığı bandın altında** (`app/core/config.py` → `RISK_MAX_CATEGORY_WEIGHT` /
  `RISK_TARGET_VOLATILITY_BAND`) — bu zaten `risk_agent.py`'nin ANA (sinyal dışı) akışında
  `_profile_position()` ile hesaplanıyor ve `"profil_konumu": "bandin_altinda"` olarak kullanıcıya
  gösteriliyor (bkz. `_compact`). Yani bu kavram bir yerde ZATEN var, sinyal sisteminin dışında.

"riskk" dokümanının örneği ("altın ağırlığı tavanın üzerine çıkmış") (b)'ye benziyor ama Sinyal 5'in
kendi veri kaynağı satırı "Portföy Ajanı (ağırlıklar) + **Anket** (profil sınırları)" diyor — bu da
(a)'nın alanı (anket = `advice_eligibility`). İkisi de savunulabilir; **hangisi kastedildiği net
değil, tek bir cümleyle teyit edilmeli** (aşağı, §5'e eklendi). Yanlış seçilirse ya var olan
`bandin_altinda` alanıyla anlamca çakışan gereksiz bir ikinci sinyal üretilir (b yorumu, mevcut
işlevi tekrar eder) ya da hiç kullanılmayan bir kod yolu (`advice_eligibility`) ilk kez sohbete
bağlanmış olur (a yorumu — muhtemelen asıl istenen budur, çünkü Sinyal 5 zaten anket/uygunluk
dünyasında yaşıyor, volatilite dünyasında değil).

**Varsayılan öneri (teyit bekliyor): (a).** `_assess_signals` içine, `holdings_result["data"]` zaten
elde varken, `allowed_asset_classes(user.risk_survey_score)` ile elde TUTULAN sınıfların farkını
alan saf bir fonksiyon eklenir; context'e yalnızca kullanılmayan (ama izinli) sınıf varsa
`kullanilmayan_kapasite` alanı eklenir. `risk_survey_score` `None` ise (anket hiç doldurulmamış) bu
kontrol atlanır — uydurma yok.

## 4. Dosya dosya değişiklik planı

### Yol A

#### 4.1 Migration (yeni, `f18c4a2e7b90`'ın üzerine)
`users` tablosuna iki nullable `DateTime(timezone=True)` kolonu:

- `risk_survey_updated_at` — anket puanı en son ne zaman yazıldı.
- `risk_survey_event_consumed_at` — bu güncelleme en son ne zaman bir risk değerlendirmesine
  yansıtıldı (tüketildi).

"Bekleyen olay var" tanımı: `risk_survey_updated_at IS NOT NULL AND (risk_survey_event_consumed_at
IS NULL OR risk_survey_event_consumed_at < risk_survey_updated_at)`. İki ayrı zaman damgası
kullanmak (tek bir boolean yerine) hem "ne zaman oldu" hem "ne zaman görüldü" bilgisini kaybetmeden
taşıyor.

#### 4.2 Model — `backend/app/models/user.py`
Yukarıdaki iki `Mapped[datetime | None]` kolonu, mevcut `risk_survey_score` bloğunun yanına aynı
gerekçe-yorumu üslubuyla eklenir.

#### 4.3 Service — `backend/app/services/user_service.py`
`set_user_risk_survey()` içine `user.risk_survey_updated_at = datetime.now(UTC)` satırı eklenir
(puan/profil yazımıyla AYNI transaction'da). `consumed_at`'e bu fonksiyon hiç dokunmaz — yeni bir
anket sonucu her zaman "tüketilmemiş" başlar.

`set_user_risk_profile()` (doğrudan/elle profil değiştirme yolu) **değişmez** — o yol zaten
`risk_survey_score`'u `None`'a düşürüyor; elle yapılan bir değişiklik hiçbir zaman "anket olayı"
sayılmamalı.

#### 4.4 Yeni MCP tool — `mcp_server/tools/risk_tools.py` içine `get_risk_survey_event`
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

#### 4.5 `agents/risk_agent.py`
`_assess_signals` içine, mevcut `get_holdings`/`get_portfolio_news` çağrılarının yanına üçüncü bir
`call_mcp_tool("get_risk_survey_event", ...)` eklenir. Tool başarısız olursa ya da `olay_var:
false` dönerse mevcut davranış aynen sürer. `olay_var: true` VE liste boş değilse
`_build_signal_context`'e yeni bir parametre eklenir, context'e SADECE bu durumda
`anket_yeniden_dolduruldu` ve `yeni_profille_izinsiz_kalan_siniflar` alanları yazılır.

Modül docstring'i üçüncü kez güncellenir ("2026-08-27 eki") — önceki iki kararın izini
silmeden, üstüne eklenerek.

#### 4.6 Prompt — `agents/prompts/risk_signals.md`
Madde 5 ve ilgili ZORUNLU KURAL satırı: "hiç kullanma" yerine "yalnızca
`anket_yeniden_dolduruldu` ve dolu bir `yeni_profille_izinsiz_kalan_siniflar` verildiyse, ve
YALNIZCA o listedeki sınıflar için tetikle" şeklinde koşullu hale getirilir. Ağırlığa bakmama
kuralı aynen kalır.

#### 4.7 Testler
- `tests/test_risk_survey_score.py`: `set_user_risk_survey` sonrası `risk_survey_updated_at`'in
  dolduğunu, `set_user_risk_profile`'ın ona dokunmadığını doğrulayan testler.
- Yeni testler (risk_tools için): olay yok / olay var+ihlal yok / olay var+ihlal var, ve tool ikinci
  kez çağrıldığında `olay_var: false` dönmesi (gerçekten tüketildiğinin kanıtı).
- `tests/test_risk_agent.py`: üçüncü tool çağrısının yapıldığı, context alanlarının SADECE doğru
  koşulda eklendiği. Mevcut `test_sinyal_baglami_anket_alanlari_hicbir_zaman_eklenmez` testi
  isim/içerik olarak güncellenmeli — artık "hiçbir zaman" değil "yalnızca olay varsa".

### Yol B

#### 4.8 `agents/risk_agent.py` — `_assess_signals` içine saf fonksiyon
`holdings_result["data"]` zaten elde varken (mevcut kod bunu Yol A için de çekiyor), yeni bir saf
fonksiyon: `_kullanilmayan_kapasite(holdings_data, risk_survey_score) -> list[AssetClass]` —
`allowed_asset_classes(risk_survey_score) - {elde tutulan sınıflar}` farkını döner.
`risk_survey_score` `None` ise (anket hiç doldurulmamış) boş liste döner, context'e hiç eklenmez.

#### 4.9 Prompt — `agents/prompts/risk_signals.md`
Madde 5'e, Yol A'nın koşullu kuralının yanına, ikinci bir koşul eklenir: context'te
`kullanilmayan_kapasite` doluysa, bu sınıflar için **bilgilendirme tonunda** (uyarı değil) bir
`profil_sapmasi` bulgusu üretilebilir — "riskk" dokümanındaki örnek ifadeye yakın ("Portföyünüz risk
profilinizin öngördüğünden daha temkinli bir yapıda"). Yol A'nın "azaltıcı" yönü ile bu yolun
"artırıcı/bilgilendirici" yönü aynı sinyal kodu (`profil_sapmasi`) altında ama farklı tonlarda —
prompt bu ayrımı net yapmalı.

**Uygulamada karşılaşılan ek bir tasarım kararı (2026-08-28, kodla birlikte alındı, analiste
DANIŞILMADI — düşük riskli bir seçim):** `RiskSignalFinding` şeması (`app/schemas/risk_signals.py`)
her bulgu için bir `asset_symbol`+`weight_percent` bekliyor — bu, Yol A'nın (elde TUTULAN, ihlal
eden bir varlık) doğal girdisi. Yol B'de ise ortada tutulan bir varlık YOK (kullanıcının o sınıftan
hiç varlığı olmaması durumu). Şema değiştirilmedi (kapsam dışı, ayrı bir karar gerektirir); bunun
yerine prompt'a şu kural eklendi: `asset_symbol`'a sınıfın adı yazılsın (ör. "Hisse Senedi (sınıf)"),
`weight_percent` 0 olsun, `contribution` her zaman "dusuk" olsun. Bu geçici/pratik bir çözümdür —
ekip isterse ileride Yol B için ayrı bir şema/alan (ör. `underused_capacity: list[AssetClass]`)
düşünülebilir.

#### 4.10 Testler
`tests/test_risk_agent.py`'ye `_kullanilmayan_kapasite` için saf fonksiyon testleri (mevcut
`_yanlis_sirket_sonuclarini_ele`/`test_market_agent.py` kalıbıyla aynı desen): kullanılmayan sınıf
var / yok / anket boş (None) / tüm izinli sınıflar zaten elde.

## 5. Analiste/ekibe götürülmesi gereken açık sorular

Bunlar benim tek başıma karar vereceğim noktalar değil:

**Yol A:**

1. **Ne zaman "tüketilsin"?** Şu anki öneri: `_assess_signals` çağrıldığı an (kullanıcı "ne
   yapmalıyım" tipi bir soru sorduğunda) — basit ama LLM o turda sinyali JSON'a koymayı
   atlarsa/hata verirse olay bir daha hiç görünmez. Alternatif: yalnızca `RiskSignalAssessment`
   BAŞARIYLA üretildiğinde tüket (daha güvenli, tool iki adımlı olur: "oku" + ayrı "tüket").
2. **Anket art arda birkaç kez değiştirilirse** (deneme-yanılma), her biri ayrı olay mı, yoksa
   sadece en son mu sayılsın? Şu anki tasarım otomatik "en son" diyor (tek `updated_at`, üzerine
   yazılıyor) — aradakiler hiç görülmez.
3. **"İzin verilmeyen ve elde olan sınıflar" hangi holdings anına göre hesaplanır** — tam sorgu
   anına göre mi (öneri budur), yoksa anketin dolduğu ana en yakın olana göre mi?

**Yol B (2026-08-28'de eklendi):**

4. ~~**"Kapasite kullanılmaması" hangi mekanizmaya bakmalı...**~~ **✅ KARARLAŞTI (2026-08-28).**
   Analist netleşti: "risk seviyesi yüksek çıktı ama daha az riskli varlıkları var" — yani (a)
   `advice_eligibility` (sınıf izinli mi/değil mi, ikili). (b) `RISK_MAX_CATEGORY_WEIGHT`/bandın
   altında kalma DEĞİL — o zaten `_profile_position`/`"bandin_altinda"` ile ana akışta ayrıca var,
   burada TEKRARLANMADI. Kod `_kullanilmayan_kapasite` (agents/risk_agent.py) bu kararla yazıldı.

## 6. Kapsam dışı — dokunulmuyor

- `RiskProfile` enum'u (4 kademe) — hâlâ bloke, bu tasarım onu değiştirmiyor.
- Mevduat kararı (`docs/notes/analiste-kapsam-sapmalari.md` madde 1) — 2026-08-28'de analist
  onayladı: mevduat kapsam dışı kalıyor. Bu tasarımla ilgisiz, ayrıca not düşülüyor.
- `set_user_risk_profile` (elle profil değiştirme) davranışı — değişmiyor.
