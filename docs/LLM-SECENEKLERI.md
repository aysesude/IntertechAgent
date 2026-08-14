# LLM Seçenekleri — Karar Notu

**Hazırlayan:** Sude · **Tarih:** 12 Ağustos 2026
**Amaç:** Akıllı Kişisel Finans Danışmanı projesinde kullanılacak dil modeli
sağlayıcısı için yönetim kararı almak

---

## Neden karar gerekiyor

Şu an prototipte, kendi sunucumuzda çalışan açık kaynak bir model kullanıyoruz
(`llama3.2:3b`). Bu seçim demo için yeterli ama iki soruyu cevaplamıyor:

1. Ürün gerçek müşteri verisiyle çalışacaksa hangi model kullanılabilir?
2. Bankanın mevcut altyapı ve sözleşmeleri hangi seçeneği zaten mümkün kılıyor?

Kod tarafında bu karar **düşük maliyetli**: `app/core/llm_client.py` içinde
sağlayıcı soyutlanmış durumda, geçiş bir yapılandırma değişikliği. Yani kararı
şimdi vermek zorunda değiliz, ama yönü bilmek mimariyi doğru kurmamızı sağlar.

---

## Belirleyici kısıt: veri nerede işleniyor

Bankacılık Kanunu ve BDDK düzenlemeleri kapsamında, bankaların faaliyetlerinde
kullandığı **birincil ve ikincil sistemlerin yurt içinde tutulması** gerektiğine
dair düzenlemeler bulunuyor. Bu, yurt dışında barındırılan bir LLM servisine
müşteri verisi göndermeyi doğrudan etkiliyor.

> **Not:** Bu değerlendirme genel bilgiye dayanıyor. Nihai yorum bankanın
> uyum ve hukuk birimlerine aittir — özellikle "prompt içine giren müşteri
> verisi"nin nasıl sınıflandırıldığı konusunda görüş alınmalı.

Ayrıca BDDK, yapay zeka modellerinin güvenilirlik, açıklanabilirlik ve şeffaflık
kriterleriyle test edilebileceği bir doğrulama çerçevesi üzerinde çalışıyor.
Seçilecek modelin **çıktısının loglanabilir ve açıklanabilir** olması ileride
gereklilik haline gelebilir.

Pratik ayrım şu:

- **Demo / PoC, sentetik veriyle** → kısıt gevşek, her seçenek konuşulabilir
- **Gerçek müşteri verisiyle** → kısıt sıkı, yurt içi veya izole çözüm gerekir

---

## Seçenekler

### 1. Kendi altyapımızda açık kaynak model

Llama, Qwen, Mistral gibi modellerin banka sunucularında çalıştırılması
(Ollama, vLLM veya benzeri).

**Artıları:** Veri hiçbir zaman kurumdan çıkmaz — uyum açısından en temiz
konum. Kullanım başına ücret yok. Model sürümü sabitlenebilir, sağlayıcının
modeli güncelleyip davranışı değiştirmesi riski yok. Denetim ve loglama
tamamen bizde.

**Eksileri:** GPU donanımı gerekiyor; ciddi kalite için tek bir 3B model
yetmez, 30B+ sınıfına çıkmak gerekir ve bu donanım yatırımı demektir.
Model güncelleme, izleme ve ölçekleme sorumluluğu ekipte. Türkçe kalitesi
en iyi kapalı modellerin gerisinde.

**Ne zaman doğru:** Veri hassasiyeti yüksekse ve donanım bütçesi varsa.

---

### 2. Azure OpenAI Service

Microsoft'un kurumsal LLM servisi. Kurumsal anlaşma kapsamında bölge seçimi
yapılabiliyor ve verilerin model eğitiminde kullanılmadığı sözleşmeyle
taahhüt ediliyor.

**Artıları:** Kalite yüksek, Türkçesi iyi. Kurumsal SLA, destek ve faturalandırma.
Banka zaten Microsoft ekosistemindeyse satın alma süreci kısa. Kimlik yönetimi
ve loglama kurumsal araçlara entegre.

**Eksileri:** Kullanım başına ücret. Veri işleme bölgesinin yurt içi
gerekliliğini karşılayıp karşılamadığı uyum birimince teyit edilmeli.
Model sürümleri Microsoft'un takvimine bağlı.

**Ne zaman doğru:** Banka Azure kullanıyorsa ve uyum birimi onay veriyorsa —
kalite/efor dengesi açısından en pratik seçenek.

---

### 3. AWS Bedrock veya Google Vertex AI

Aynı mantık, farklı sağlayıcı. Bedrock birden fazla model ailesini (Anthropic,
Meta, Mistral) tek arayüzden sunuyor; Vertex AI Google'ın modellerini.

**Artıları:** Banka zaten o bulutu kullanıyorsa ek tedarikçi süreci gerekmez.
Bedrock'ta model çeşitliliği fazla, sağlayıcıya bağımlılık daha düşük.

**Eksileri:** Azure ile aynı veri konumu soruları. Bankanın o bulutla mevcut
anlaşması yoksa satın alma süreci uzun.

---

### 4. Doğrudan OpenAI / Anthropic API

Sağlayıcının kendi API'si üzerinden, kurumsal bulut aracısı olmadan.

**Artıları:** En hızlı başlangıç, en güncel modeller, en düşük entegrasyon eforu.

**Eksileri:** Veri yurt dışına çıkıyor. Bankacılık düzenlemeleri açısından
**gerçek müşteri verisiyle kullanımı büyük olasılıkla mümkün değil.**
Kurumsal sözleşme ve denetim izi sınırlı.

**Ne zaman doğru:** Yalnızca sentetik veriyle çalışan prototip ve karşılaştırma
testleri için.

---

### 5. Hibrit yaklaşım

Hassas veri içeren işlemler (portföy hesabı, müşteri bilgisi) yerel modelde;
hassas olmayan işlemler (genel finansal metin özetleme, haber yorumlama)
bulut modelinde.

**Artıları:** Maliyet ve uyum arasında denge. Kritik veri hiç dışarı çıkmıyor.

**Eksileri:** İki sistemi birden yönetmek, iki farklı davranışı test etmek.
Hangi isteğin nereye gideceğine karar veren katman ek karmaşıklık.

**Not:** Mevcut mimarimiz buna hazır — ajan bazında farklı LLM istemcisi
kullanmak yapısal olarak mümkün.

---

## Karşılaştırma

| | Veri nerede | Maliyet modeli | Türkçe kalitesi | Kurulum eforu | Uyum riski |
|---|---|---|---|---|---|
| Kendi sunucumuz | Kurum içi | Donanım (sabit) | Orta | Yüksek | Düşük |
| Azure OpenAI | Seçilen bölge | Token başına | Yüksek | Düşük | Orta |
| AWS Bedrock | Seçilen bölge | Token başına | Yüksek | Düşük | Orta |
| Vertex AI | Seçilen bölge | Token başına | Yüksek | Düşük | Orta |
| Doğrudan API | Yurt dışı | Token başına | Yüksek | Çok düşük | Yüksek |
| Hibrit | Karma | Karma | Yüksek | Yüksek | Düşük |

---

## Yöneticiye sorulacaklar

Kararı verebilmek için bu altı sorunun cevabına ihtiyacımız var:

1. **Bankanın mevcut bir bulut anlaşması var mı?** (Azure / AWS / GCP)
   Varsa seçenek listesi kendiliğinden daralır ve satın alma süreci kısalır.

2. **Prompt'a giren müşteri verisi hangi sınıfta değerlendiriliyor?**
   Uyum biriminin görüşü, yurt dışı seçenekleri tamamen elemeye yeter.

3. **Bu proje bir prototip mi, ürün adayı mı?** Prototipse sentetik veriyle
   devam edip kararı ertelemek mantıklı. Ürün adayıysa şimdi karar verilmeli.

4. **GPU donanımı veya bütçesi mevcut mu?** Kendi altyapımızda ciddi kalitede
   model çalıştırmanın ön koşulu bu.

5. **Model çıktılarının denetlenebilir olması bekleniyor mu?** BDDK'nın
   üzerinde çalıştığı doğrulama çerçevesi göz önüne alınırsa, loglama ve
   açıklanabilirlik gereksinimlerini baştan tasarlamak akıllıca olur.

6. **Kim onaylayacak?** Bilgi güvenliği, uyum ve mimari birimlerinden hangisinin
   imzası gerekiyor?

---

## Önerim

**Kısa vade (staj süresi):** Mevcut kurulumla devam edelim — kendi sunucumuzda
açık kaynak model, sentetik veri. Hiçbir uyum sorusu doğurmuyor, maliyeti sıfır
ve demo için yeterli.

**Orta vade (ürünleşirse):** Banka zaten Azure kullanıyorsa **Azure OpenAI**
en pratik yol. Kullanmıyorsa ya da veri kısıtı katıysa **kendi altyapımızda
daha büyük bir açık kaynak model** doğru yön olur.

Her iki durumda da kod değişikliği minimum — sağlayıcı soyutlaması bunun için
tasarlandı.

---

**Kaynaklar:** [Bankacılık mevzuatında veri aktarımı ve saklanması (Gün + Partners)](https://gun.av.tr/tr/goruslerimiz/guncel-yazilar/bankacilik-mevzuatinda-veri-aktarimi-ve-saklanmasina-dair-yeni-duzenlemeler) · [BDDK ve KKB Yapay Zeka ve Bulut Teknolojileri Çalıştayı, Şubat 2026](https://fintechistanbul.org/2026/02/26/bddk-ve-kredi-kayit-burosu-ev-sahipliginde-yapay-zeka-ve-bulut-teknolojileri-calistayi-duzenlendi/)
