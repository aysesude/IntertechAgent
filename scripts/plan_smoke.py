"""Planlayıcı duman testi: LLM her soru için doğru tool'u seçiyor mu.

Faz 2 matematiği yazılmadan önce, ajan planlamasının gerçek modelle çalıştığını
doğrulamak için. Stub servisler NotImplementedError attığı için özet metninde
hata görmek normaldir; burada bakılan tek şey `selected_tools`.

Kullanım:
    docker compose exec -w / api python scripts/plan_smoke.py <user_id>
"""

import asyncio
import sys

from agents.base import AgentRequest
from agents.portfolio_agent import PortfolioAgent
from app.core.config import settings

SORULAR = [
    ("portföyümde ne var, dağılımım nasıl?", "get_portfolio_summary"),
    ("hangi varlığımda ne kadar kâr var?", "get_holdings"),
    ("son 3 ayda portföyüm nasıl gitti?", "get_portfolio_performance"),
    ("geçen ay hangi alım satımları yaptım?", "get_transactions"),
    ("portföyüm BIST100'e göre nasıl gidiyor?", "get_benchmark_comparison"),
]


async def main(user_id: str) -> None:
    ajan = PortfolioAgent(mcp_server_url=settings.mcp_server_url)
    basarili = 0
    for soru, beklenen in SORULAR:
        cevap = await ajan.execute(AgentRequest(user_id=user_id, session_id="smoke", query=soru))
        veri = cevap.data or {}
        secilen = veri.get("selected_tools", [])
        dusen = veri.get("failed_tools", [])
        tutdu = beklenen in secilen
        basarili += tutdu
        print(f"{'OK ' if tutdu else '!! '}{soru}")
        print(f"   beklenen : {beklenen}")
        print(f"   secilen  : {secilen}")
        if dusen:
            print(f"   dusen    : {dusen}  (Faz 2 stub'i ise beklenen durum)")
        if cevap.error:
            print(f"   hata     : {cevap.error}")
        print(f"   ozet     : {cevap.summary_text[:200] or '(bos)'}")
        print("-" * 70)
    print(f"\nSonuc: {basarili}/{len(SORULAR)} soruda dogru tool secildi.")
    print("Not: tool'un stub olmasi plan basarisini etkilemez; 'secilen'e bakilir.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Kullanim: python scripts/plan_smoke.py <user_id>")
    asyncio.run(main(sys.argv[1]))
