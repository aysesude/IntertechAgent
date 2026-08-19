# Orkestratör LLM (Faz 1) Güncellemesi

**Tarih:** 18 Ağustos 2026

## Amaç
Bu güncellemenin amacı, `agents/orchestrator.py` dosyasındaki katı kural tabanlı (regex/anahtar kelime) yönlendirme mantığını kaldırıp yerine LLM (ChatOllama) tabanlı dinamik bir bağlayıcı (connector) mimarisi kurmaktır. 

Önceki yapıda `_PORTFOLIO_KEYWORDS` ve `_MARKET_KEYWORDS` listeleri üzerinden arama yapılıyordu. Bu durum, kullanıcının farklı kelimelerle aynı amacı ifade etmesi (örn. "hesabım", "portföyüm", "param") durumunda eşleşmemelere ve kodun giderek şişmesine neden oluyordu.

## Yapılan Değişiklikler

1. **`detect_intent` Metodunun LLM'e Geçirilmesi:**
   Kullanıcıdan gelen mesaj `app.core.llm_client.get_llm_client()` üzerinden ChatOllama'ya verilerek intent (niyet) tespiti yapılması sağlandı. LLM sadece `PORTFOLIO`, `MARKET` veya `BOTH` olarak cevap döndürür. Bu sayede karmaşık cümle yapıları veya ima yoluyla sorulan sorular da doğru bir şekilde ilgili ajana yönlendirilebilir.

2. **`merge_responses` Metodunun LLM ile Harmanlanması:**
   Sorgu "BOTH" (her iki alanı da kapsayan) olduğunda, daha önce sadece string birleştirme (`\n\n.join`) yapılıyordu. Artık `merge_responses` metodu da `ChatOllama`'yı kullanarak, iki farklı ajan tarafından döndürülen özet metinleri tekil, akıcı ve pürüzsüz bir Türkçe paragraf (sanki tek bir uzman konuşuyormuş gibi) halinde harmanlıyor.

## İleriye Dönük (3+ Ajan) Genişletme Vizyonu
Şu an sistemde aktif olarak `portfolio_agent` ve `market_agent` çalışmaktadır (RAG sistemi market_agent üzerinden entegre edilmiştir). Gelecekte, örneğin `risk_agent` (Risk Ajanı) tamamen hazır olduğunda Orkestratörü genişletmek son derece basit olacaktır:

1. `detect_intent` içindeki System Prompt'a `"Eğer kullanıcı portföyünün risk oranını, volatilitesini sorarsa: RISK dön."` kuralı eklenecek.
2. `agents/orchestrator.py` içindeki LangGraph grafiğine (`_build_graph`) `run_risk_agent` node'u ve edge'leri eklenecek.

Mevcut şemalarda (`AgentResponse` vb.) veya MCP Tool sözleşmelerinde hiçbir değişiklik yapmadan sistem anında 3'lü, 4'lü çoklu-ajan orkestrasyonunu destekleyecektir.
