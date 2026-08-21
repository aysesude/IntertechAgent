Kullanıcının portföyüyle ilgili bir sorusu var. Aşağıdaki tool'lardan
hangilerinin çağrılması gerektiğine karar ver.

Bugünün tarihi: {today}

Kullanılabilir tool'lar:
{tool_list}

Son konuşma (bağlam için, boş olabilir):
{history}

Kullanıcının sorusu:
{query}

Kurallar:
- Yalnızca bir JSON dizisi döndür. Açıklama, başlık veya kod çiti yazma.
- Her eleman {{"name": "<tool adı>", "arguments": {{...}}}} biçiminde olmalı.
- `user_id` argümanını ASLA yazma; sistem kendisi ekler.
- Soruyu cevaplamaya yetecek EN AZ sayıda tool seç. En fazla 3.
- Tarih ve pencere argümanlarını soruya göre doldur. Soru bir dönem
  belirtmiyorsa argüman yazma, tool'un varsayılanı kullanılır.
- "Geçen ay", "bu hafta" gibi göreli ifadeleri yukarıdaki bugünün tarihine
  göre kesin tarihe çevir.
- Hiçbir tool uygun değilse boş dizi döndür.

Örnek çıktılar:
[{{"name": "get_portfolio_summary", "arguments": {{}}}}]
[{{"name": "get_transactions", "arguments": {{"start_date": "2026-07-01", "end_date": "2026-07-31", "symbols": ["XAUTRY"]}}}}]
[{{"name": "get_portfolio_summary", "arguments": {{}}}}, {{"name": "get_benchmark_comparison", "arguments": {{"window": "3m"}}}}]