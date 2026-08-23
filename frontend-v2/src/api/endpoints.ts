/**
 * Ekran verisi uçları.
 *
 * BURASI ŞU AN BİLEREK BOŞ. Tasarım deposundan gelen ilk hâli `GET /dashboard`,
 * `GET /portfolio`, `GET /risk`, `GET /market`, `GET /chat` uçlarını çağırıyordu
 * — bu projenin backend'inde böyle uçlar YOK. Uçlar `/api/portfolio/{user_id}`,
 * `/api/portfolio/{user_id}/holdings`, `/api/chat` (SSE) gibi ve **ham veri**
 * döndürüyor; ekranlar ise `src/types/finance.ts`'teki görünüm modelini
 * bekliyor (camelCase, önceden biçimlendirilmiş metinler).
 *
 * Aradaki dönüşüm `src/adapters/` altında saf fonksiyonlarla yapılacak ve her
 * ekran sırayla bağlanacak (bkz. frontend-v2/README.md). Bağlanmamış ekranlar
 * `useApiResource(null, mock)` ile çağrılır: boşa HTTP isteği atılmaz ve durum
 * `isDemoData: true` ile açıkça işaretlenir — "sunucudan geldi" ile "tasarım
 * verisi" birbirine karışmasın.
 *
 * Kimlik doğrulama uçları ayrı dosyada: `src/api/auth.ts`.
 */

export {};
