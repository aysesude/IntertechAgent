# frontend-v2 — VİRA arayüzü

Projenin **yeni** arayüzü. Mevcut `frontend/` ile **yan yana** koşar, onun yerine
geçmez: çalışan sistem kırılmasın diye ayrı klasör, ayrı port (5174), ayrı docker
servisi. Parite sağlandığında `frontend/` emekliye ayrılıp isimler takas edilecek.

Kaynağı ayrı bir tasarım deposudur (`interntech_ui/vira-dashboard`); bileşenler
oradan olduğu gibi taşındı, tasarım geçmişi bu depoda yok.

## Çalıştırma

Docker ile (önerilen — kök dizinden):

```bash
docker compose up --build frontend-v2
```

http://localhost:5174

Konteyner dışında:

```bash
cd frontend-v2 && cp .env.example .env && npm install && npm run dev
```

## Mimari

- `src/types/finance.ts` — ekranların tükettiği **görünüm modeli** tipleri.
  Backend şemasıyla (`backend/app/schemas/`) birebir aynı DEĞİL: camelCase,
  önceden biçimlendirilmiş metin alanları (`formattedValue`) içeriyor.
- `src/data/mockData.ts` — tasarımdan çıkarılan sabit veri. Backend bağlanana
  kadar ekranları besler, sonrasında da tasarım referansı olarak kalır.
- `src/api/client.ts`, `src/api/endpoints.ts` — tipli fetch katmanı.
- `src/hooks/*` — ekran başına `useXData()`; API tanımlıysa canlı veri dener.
- `src/components/*`, `src/pages/*` — sunum bileşenleri, veriyi **prop olarak**
  alır, kendileri fetch çağırmaz.

### Backend'e bağlanırken: adapter katmanı

Backend **ham veri** döndürür (`snake_case`, `Decimal`→`float`), ekranlar ise
yukarıdaki görünüm modelini bekler. Dönüşüm `src/adapters/` altında saf
fonksiyonlarla yapılır — bileşenlere dokunulmaz, dönüşüm birim testlenebilir.

## Bilinen borçlar (entegrasyon sırasında kapanacak)

- **`useApiResource` istek hata verince sessizce mock veriye düşüyor** ve
  sayfalar `error` alanını okumuyor. Backend düşerse ekranda uydurma rakamlar
  gerçekmiş gibi görünür — finansal bir üründe kabul edilemez (CLAUDE.md §4).
  Mock yalnızca `VITE_API_BASE_URL` tanımsızken devreye girmeli.
- `RiskProfile.score` 0-100 bekliyor; backend v2 kompozit skoru bilerek kaldırdı,
  yerine 7 kademeli etiket + yıllık volatilite var.
- `PerformancePoint.bist` — varlık evreninde `XU100` yok (`providers/universe.py`).
- `PortfolioSummary.realReturnPct` (enflasyondan arındırılmış) — sistemde
  enflasyon kaynağı yok.
- `AssetClassId` içinde `crypto` var, backend'in 5 varlık sınıfında yok.
- Sohbet `postChatMessage` ile tek parça yanıt bekliyor; backend SSE ile
  **streaming** yapıyor (`frontend/src/api/chat.ts` bunu çözmüş, taşınacak).
