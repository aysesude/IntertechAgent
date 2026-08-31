# Risk Ajanı — Akış Şeması Karşılaştırması (2026-08-28)

**Kaynak:** Yağız'ın elle çizdiği akış şeması. Üç kutu:

```
                    ┌─→ yoğunlaşma var mı ───────────┐
portföy bilgisi ────┼─→ profilin risk profiline ──────┼──→ çıktı
                    │   uyuyor mu (değişmesi          │
                    │   durumu)                       │
                    └─→ varlık çeşitleri ile ilgili ──┘
                        haberleri yorum
```

Tek girdi (portföy bilgisi), üç paralel soru, tek çıktı. Aşağıda her kutunun kodda karşılığı ve
GERÇEK durumu var — tahmin değil, bu oturumda okunan koda dayanıyor.

---

## 1. "Yoğunlaşma var mı" → Sinyal 1 (konsantrasyon)

**Durum: UYGULANMIŞ, çalışıyor.**

`agents/prompts/risk_signals.md` madde 1: portföy ağırlıklarından (tek varlığın payı, en büyük
2-3 varlığın toplam payı) LLM'e yorumlatılıyor. Eşik yok, kasıtlı — "riskk" dokümanı da aynen bunu
istiyor ("Eşik vermeyin... ajan dağılımın şeklini görür ve yorumlar"). Veri kaynağı yalnızca
`get_holdings` — kaynak dokümana ihtiyaç yok. Akış şemasındaki kutuyla birebir örtüşüyor.

## 2. "Profilin risk profiline uyuyor mu (değişmesi durumu)" → Sinyal 5 (profil_sapmasi)

**Durum: KOD TARAFI YOK. Şemanın üç kutusundan en az hazır olanı bu — ama şemada diğer ikisiyle
eşit ağırlıkta bir ana pilar olarak duruyor.**

Şemadaki parantez içi not — **"(değişmesi durumu)"** — kelimesi kelimesine bu oturumda analistten
gelen cevapla örtüşüyor: sinyal PROFİLİN DEĞİŞTİĞİ durumda tetiklenmeli. Bu, Sinyal 5'in olay tabanlı
yolunu (Yol A — anket yenilendi, yeni profil eskisinden düşük, elde artık izinsiz bir sınıf kaldı)
doğrudan doğruluyor.

Bugünkü kod (`agents/risk_agent.py`) bu kutuyu LLM'e **hiç göstermiyor** — Sinyal 5 kalıcı dormant,
`agents/prompts/risk_signals.md` LLM'e "bu sinyali hiç kullanma" diyor. Yani akış şemasının üç ana
sorusundan biri şu an **çıktıya hiç yansımıyor**. Tasarım hazır (`docs/notes/
sinyal5-olay-tabanli-aktivasyon-tasarimi.md`, Yol A + Yol B), kod yazılmadı.

**Bu şema, Sinyal 5'in "nice to have" değil şemanın üç direğinden biri olduğunu gösteriyor —
önceliklendirme için güçlü bir kanıt.**

## 3. "Varlık çeşitleri ile ilgili haberleri yorum" → Sinyal 3 (olumsuz_haber) + Sinyal 4 (sektor_gelismesi)

**Durum: KISMEN. Varlık bazlı haber yorumu çalışıyor; sektör bazlı olan fiilen hiç tetiklenmiyor.**

- **Sinyal 3 (olumsuz_haber) — çalışıyor.** `get_portfolio_news`'ten gelen, varlığa doğrudan bağlı
  doküman parçaları LLM'e veriliyor; kaynak zorunlu, yoksa üretilmiyor.
- **Sinyal 4 (sektor_gelismesi) — kodda TANIMLI ama önkoşulu eksik.** Sektör düzeyinde bir gelişmeyi
  değerlendirebilmek için varlık↔sektör eşleme tablosu gerekiyor (`agents/risk_agent.py` modül
  docstring'i: "Sektör verisi bilerek YOK — henüz üretilmedi, ekipte Çağan'ın görevi"). Bu tablo
  olmadan LLM'e sektör bilgisi hiç gitmiyor, sinyal fiilen hiç tetiklenmiyor. "riskk" dokümanı da bu
  önkoşulu ayrıca vurguluyor.
- **Makro haberler** (Tahvil/Döviz/Altın/Nakit için, şirket bilançosu olmayan sınıflar) ayrı bir
  kanaldan (`_fetch_macro_context`) geliyor ama SİNYAL TETİKLEMEK için değil, yalnızca
  `investment_strategy` metnini beslemek için — bu bilinçli bir ayrım, akış şemasıyla çelişmiyor.

## Çıktı

Şemanın sağ ucundaki "çıktı" kutusu, kodda `RiskSignalAssessment` şemasına karşılık geliyor:
`risk_level` (5 kademe), `risky_assets` (her biri sinyal listesi + katkı düzeyi + kaynak),
`rebalancing`, `investment_strategy`, `confidence`. Bu kısım şemayla uyumlu; sorun kutulardan
BİRİNİN (profil uyumu) çıktıya hiç girmemesi.

---

## Sinyal 2 (sektor_yogunlasmasi) neden şemada yok?

"riskk" dokümanındaki 5 sinyalden biri (sektör yoğunlaşması — dağınık görünen ama tek sektöre bağlı
portföy) bu 3 kutuluk şemada ayrı bir dal olarak görünmüyor; muhtemelen "varlık çeşitleri ile ilgili
haberler" kutusunun bir parçası sayılmış ya da şema bu ayrıntıyı basitleştirmiş. Kodda (prompt
seviyesinde) tanımlı ama Sinyal 4 ile aynı önkoşula (sektör eşleme tablosu) bağlı, o da fiilen
tetiklenmiyor. Şemayla kod arasında burada bir çelişki yok, yalnızca şemanın detay seviyesi düşük.

---

## Özet tablo

| Şema kutusu | Sinyal(ler) | Kod durumu |
|---|---|---|
| Yoğunlaşma var mı | 1 — konsantrasyon | ✅ Çalışıyor |
| Profil uyuyor mu (değişmesi durumu) | 5 — profil_sapmasi | ❌ Dormant, kod yok (tasarım hazır) |
| Varlık haberleri yorumu | 3 — olumsuz_haber | ✅ Çalışıyor |
| (aynı kutu, sektör boyutu) | 4 — sektor_gelismesi | ⚠️ Tanımlı ama önkoşulu (sektör tablosu) yok, fiilen hiç tetiklenmiyor |
| (şemada yok, dokümanda var) | 2 — sektor_yogunlasmasi | ⚠️ Aynı önkoşula bağlı, fiilen hiç tetiklenmiyor |

**Sonuç:** Şemanın üç ana sorusundan ikisi kodda çalışıyor, biri (profil uyumu — Sinyal 5) tamamen
boşta. Dokümandaki 5 sinyalden ikisi (2 ve 4) ortak bir önkoşul (sektör-varlık eşleme tablosu)
eksikliğinden dolayı fiilen hiç üretilmiyor. Yani şu an gerçekte çalışan: Sinyal 1 ve 3 — beşte iki.
