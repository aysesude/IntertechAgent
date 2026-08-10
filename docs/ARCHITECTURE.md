# Mimari

## Bileşen diyagramı

```mermaid
graph TB
    subgraph Client["Tarayıcı"]
        FE["Frontend<br/>React + Vite + TS<br/>Recharts, TanStack Query"]
    end

    subgraph API_Service["api servisi (FastAPI)"]
        API["REST API<br/>app/api/*"]
        SVC["Servis katmanı<br/>app/services/* (tüm SQL burada)"]
        ORCH["Orchestrator<br/>agents/orchestrator.py (LangGraph)"]
    end

    subgraph Agents["Ajanlar (api servisi içinde çalışır)"]
        PA["Portföy Ajanı<br/>çalışıyor"]
        MA["Piyasa Araştırma Ajanı<br/>iskelet"]
        RA["Risk/Strateji Ajanı<br/>iskelet"]
    end

    subgraph MCP_Service["mcp_server servisi"]
        MCP["MCP Server (fastmcp)<br/>get_portfolio_summary"]
    end

    subgraph Data["Veri katmanı"]
        PG[("PostgreSQL 16")]
        CHROMA[("Chroma<br/>vektör DB, iskelet")]
    end

    subgraph External["Host makine"]
        OLLAMA["Ollama<br/>llm_client.py üzerinden"]
    end

    FE -- "GET /api/portfolio/{user_id}" --> API
    FE -- "POST /api/chat (SSE)" --> API
    API --> SVC
    API --> ORCH
    SVC --> PG
    ORCH --> PA
    ORCH -.-> MA
    ORCH -.-> RA
    PA -- "MCP tool call (HTTP)" --> MCP
    MCP --> SVC
    PA -- "prompt" --> OLLAMA
    MA -.-> CHROMA

    style MA stroke-dasharray: 5 5
    style RA stroke-dasharray: 5 5
    style CHROMA stroke-dasharray: 5 5
```

Kesikli çizgiler henüz uygulanmamış (iskelet) bileşenleri/bağlantıları gösterir.

## Veri akışı: `POST /api/chat`

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as api (FastAPI)
    participant ORCH as Orchestrator (LangGraph)
    participant PA as PortfolioAgent
    participant MCP as MCP Server
    participant SVC as portfolio_service
    participant DB as PostgreSQL
    participant LLM as Ollama

    FE->>API: POST /api/chat {user_id, session_id, message}
    API->>DB: kullanıcı mesajını kaydet (agents çalışmadan önce)
    API-->>FE: event: session
    API->>ORCH: stream_orchestrator(...)
    ORCH->>PA: execute(request, on_token=...)
    PA->>MCP: call_tool("get_portfolio_summary", {user_id})
    MCP->>SVC: get_portfolio_summary(db, user_id)
    SVC->>DB: SQL (holdings, en güncel fiyatlar)
    DB-->>SVC: satırlar
    SVC-->>MCP: PortfolioSummary
    MCP-->>PA: {"success": true, "data": {...}}
    PA->>LLM: stream(prompt + portföy JSON)
    loop her token
        LLM-->>PA: token
        PA-->>ORCH: on_token(delta)
        ORCH-->>API: ("custom", {"delta": ...})
        API-->>FE: event: token
    end
    API->>DB: asistan mesajını kaydet (complete/incomplete)
    API-->>FE: event: done {agent, final_answer, data}
```

## Neden bu şekilde

- **Ajanlar veriye doğrudan erişmez**, sadece MCP Server üzerindeki tool'ları
  çağırır; tool'lar da servis katmanını çağırır. Bu, "sayısal hiçbir değer
  LLM tarafından üretilmez" ilkesini kod seviyesinde zorunlu kılar — LLM'in
  eline hiçbir zaman ham DB erişimi geçmez.
- **`app/services/`** tüm SQL sorgularının tek adresi; hem REST API hem MCP
  tool'u aynı fonksiyonları çağırır, mantık tekrarlanmaz.
- **Orchestrator**, LangGraph'in `stream_mode="custom"` + `writer` enjeksiyonu
  sayesinde hem tek seferlik (`run_orchestrator`) hem stream'li
  (`stream_orchestrator`) çağrıyı aynı graf üzerinden, kod tekrarı olmadan
  destekler.
- **Chroma ve Ollama** ayrı container'lar olarak `docker-compose.yml`'da var
  (Ollama hariç — bkz. [README](../README.md#neden-ayrı-bir-ollama-containerı-yok)),
  ileride farklı vektör DB / LLM sağlayıcılarına geçişi kolaylaştırmak için
  soyutlanmış arayüzler (`rag/vector_store.py`, `app/core/llm_client.py`)
  arkasında saklı.
