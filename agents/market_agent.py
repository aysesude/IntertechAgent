"""Piyasa Araştırma Ajanı. RAG altyapısı kullanılarak yapılandırılmıştır."""

from collections.abc import Callable
import traceback

from agents.base import AgentRequest, AgentResponse, BaseAgent
from rag.pipeline import FinancialRAGAssistant


class MarketAgent(BaseAgent):
    agent_name = "market_agent"
    
    def __init__(self, mcp_server_url: str) -> None:
        super().__init__(mcp_server_url)
        # RAG Assistant başlatılıyor. Model ağırlıklarını ve chroma'yı yükler.
        self.rag_assistant = FinancialRAGAssistant(
            persist_directory="./chroma_db",
            mapping_config_path="./data/company_mappings.json"
        )

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        try:
            # RAG asistanına soruyu iletiyoruz
            response_text = await self.rag_assistant.chat_async(request.query, session_id=request.session_id)
            
            if on_token:
                on_token(response_text)
            
            return AgentResponse(
                agent_name=self.agent_name,
                success=True,
                summary_text=response_text,
                data={"session_id": request.session_id, "query": request.query}
            )
            
        except Exception as e:
            error_msg = f"MarketAgent çalıştırılırken bir hata oluştu: {str(e)}\n{traceback.format_exc()}"
            return self.error_response(error_msg)
