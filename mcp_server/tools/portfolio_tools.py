"""Portföy tool'ları.

Kurallar: tool veriye doğrudan erişmez, her zaman app.services üzerinden okur;
sayısal hiçbir değer burada hesaplanmaz; zarfı `@tool_handler` kurar, gövde
yalnızca veriyi döndürür.

Docstring'ler dokümantasyon değil **prompt parçasıdır**: Portföy Ajanı bu beş
tool arasından seçimini `client.list_tools()` ile okuduğu bu metinlere bakarak
yapıyor (agents/portfolio_agent.py). "Ne zaman kullanılmaz" satırları bu yüzden
komşu tool'ları tek tek anıyor.
"""

from datetime import date
from typing import Any
from uuid import UUID

from fastmcp import FastMCP

from app.core.config import AssetClass, TimeWindow

# Takma adlar zorunlu: aşağıdaki tool fonksiyonlarının adı servis
# fonksiyonlarıyla aynı, takma ad olmadan tool kendi kendini çağırırdı.
# Beş ayrı satır isort'un varsayılan davranışı (combine-as-imports kapalı).
from app.services.portfolio_service import (
    get_benchmark_comparison as fetch_benchmark,
)
from app.services.portfolio_service import (
    get_holdings_valuation as fetch_holdings,
)
from app.services.portfolio_service import (
    get_portfolio_performance as fetch_performance,
)
from app.services.portfolio_service import (
    get_portfolio_summary as fetch_portfolio_summary,
)
from app.services.portfolio_service import (
    get_transactions as fetch_transactions,
)
from mcp_server.tools._base import db_session, tool_handler


def register(mcp: FastMCP) -> list[str]:
    @mcp.tool(name="get_portfolio_summary")
    @tool_handler()
    def get_portfolio_summary(user_id: UUID) -> dict[str, Any]:
        """Bir kullanıcının portföyünün tek seferlik özetini döndürür.

        Ne zaman kullanılır: "portföyüm ne durumda", "toplam değerim ne kadar",
        "dağılımım nasıl", "kâr mı zarar mı ettim" gibi bütünsel sorular.

        Ne zaman kullanılmaz: tek tek varlıkların listesi isteniyorsa
        (get_holdings), zaman içindeki performans/geçmiş getiri soruluyorsa
        (get_portfolio_performance), işlem geçmişi soruluyorsa
        (get_transactions), endekslerle kıyaslama isteniyorsa
        (get_benchmark_comparison), risk veya yeniden dengeleme soruluyorsa
        (get_risk_assessment).

        Args:
            user_id: Portföy özeti istenen kullanıcının UUID'si.

        Returns:
            Başarılı: {"success": true, "data": {"user_id": ..., "as_of":
            "2026-08-20", "total_value": 125430.5, "total_cost_basis": ...,
            "net_invested": ..., "total_gain_loss": {"amount": ..., "percent":
            ...}, "allocation": [{"asset_class": "stock", "value": ...,
            "percent": ...}, ...], "holdings_count": 7}}. Tüm tutarlar TRY,
            sayı (string değil).
            Hata: {"success": false, "error": {"code": "NOT_FOUND",
            "message": "..."}} — kullanıcının portföyü yoksa.

            İki taban karıştırılmamalı: `total_cost_basis` elde tutulan
            varlıkların maliyetidir (serbest nakit hariç), `net_invested`
            dışarıdan konan net sermayedir (yatırma − çekme, nakit dahil).
            `total_gain_loss` **net_invested'a göre** hesaplanır ve
            `total_value - net_invested`'a eşittir. Kullanıcıya "maliyet"
            değil "yatırılan tutar" gösterilmeli ki üç rakam birbirini tutsun.
        """
        with db_session() as db:
            return fetch_portfolio_summary(db, user_id).model_dump(mode="json")

    @mcp.tool(name="get_holdings")
    @tool_handler()
    def get_holdings(user_id: UUID) -> dict[str, Any]:
        """Portföydeki varlıkları tek tek, değer ve kâr/zarar bilgisiyle listeler.

        Ne zaman kullanılır: "hangi varlıklarım var", "en çok kazandıran
        yatırımım hangisi", "portföyümün yüzde kaçı hisse", "X hissesinden
        kârda mıyım" gibi varlık kırılımı gerektiren sorular. En iyi ve en kötü
        performans gösteren varlık da bu çağrıda döner.

        Ne zaman kullanılmaz: yalnızca toplam değer ve sınıf dağılımı
        yeterliyse (get_portfolio_summary), zaman içindeki değişim soruluyorsa
        (get_portfolio_performance), alım/satım geçmişi soruluyorsa
        (get_transactions), endekslerle kıyaslama isteniyorsa
        (get_benchmark_comparison).

        Args:
            user_id: Varlıkları listelenecek kullanıcının UUID'si.

        Returns:
            Başarılı: data.holdings = her varlık için symbol, name,
            asset_class, quantity, current_price_try, market_value_try,
            weight_percent, avg_cost_try, cost_basis_try, unrealized_pnl_try,
            unrealized_pnl_percent, realized_pnl_try. Ayrıca
            data.best_performer ve data.worst_performer.
            Fiyatı bulunamayan varlık price_missing=true ile döner, değer
            alanları null'dur ve ağırlık hesabına girmez.
            Hata: NOT_FOUND — portföy yoksa.
        """
        with db_session() as db:
            return fetch_holdings(db, user_id).model_dump(mode="json")

    @mcp.tool(name="get_portfolio_performance")
    @tool_handler()
    def get_portfolio_performance(
        user_id: UUID, window: TimeWindow = TimeWindow.M1
    ) -> dict[str, Any]:
        """Portföyün zaman içindeki değerini ve dönemsel değişimini döndürür.

        Ne zaman kullanılır: "son 1 ayda ne kadar kazandım", "portföyüm nasıl
        gidiyor", "bu hafta ne değişti", "6 ayda getirim ne oldu" gibi zaman
        boyutu olan sorular.

        Ne zaman kullanılmaz: anlık durum soruluyorsa
        (get_portfolio_summary), varlık kırılımı soruluyorsa (get_holdings),
        tek tek işlemler soruluyorsa (get_transactions), endeksle
        karşılaştırma isteniyorsa (get_benchmark_comparison).

        Args:
            user_id: Kullanıcının UUID'si.
            window: Serinin kapsayacağı pencere: 1m, 3m, 6m, 12m. Varsayılan
                1m. Portföy bu pencereden gençse başlangıç ilk işleme kırpılır
                ve truncated_to_inception=true döner.

        Returns:
            Başarılı: data.series (grafik için: date, value_try, invested_try)
            ve data.summary (start_value, end_value, change_amount,
            change_percent, realized_pnl, unrealized_pnl, changes.daily/
            weekly/monthly). invested_try yalnızca dış para akışıdır
            (yatırılan − çekilen); değerle arasındaki fark toplam kârdır.
            Hesaplanamayan dönemsel değişim null döner, 0 değil.
            Hata: NOT_FOUND · INSUFFICIENT_DATA.
        """
        with db_session() as db:
            return fetch_performance(db, user_id, window).model_dump(mode="json")

    @mcp.tool(name="get_transactions")
    @tool_handler()
    def get_transactions(
        user_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
    ) -> dict[str, Any]:
        """Kullanıcının alım/satım ve nakit hareketlerini listeler.

        Ne zaman kullanılır: "geçen ay ne kadar altın aldım", "THYAO'yu kaç
        liradan almışım", "ne zaman sattım", "bu yıl kaç işlem yaptım" gibi
        işlem geçmişi soruları.

        Ne zaman kullanılmaz: şu anki pozisyon soruluyorsa (get_holdings),
        toplam değer soruluyorsa (get_portfolio_summary), getiri soruluyorsa
        (get_portfolio_performance).

        Args:
            user_id: Kullanıcının UUID'si.
            start_date: Başlangıç tarihi, dahil (YYYY-AA-GG). Verilmezse ilk
                işlemden başlar.
            end_date: Bitiş tarihi, dahil. Verilmezse bugüne kadar.
            symbols: Yalnızca bu sembollerin işlemleri, ör. ["XAUTRY"].
                Verilmezse tüm işlemler, nakit hareketleri dahil.
            asset_class: Yalnızca bu varlık sınıfının işlemleri: stock,
                precious_metal, currency, bond, cash. "Hangi HİSSELERİ aldım",
                "altın işlemlerim" gibi SINIF bazlı sorular için — hangi
                sembolün hangi sınıfta olduğunu bilmene gerek kalmaz.

        Returns:
            Başarılı: data.transactions = [{transaction_date, type, symbol,
            quantity, price, currency, fx_rate_to_try, fee_try,
            cash_amount_try, position_after}]. cash_amount_try işaretlidir ve
            işlem anındaki kurla dondurulmuştur: o gün hesaptan fiilen çıkan
            veya giren TL budur. position_after işlemden sonraki toplam
            pozisyondur.
            Hata: NOT_FOUND · INVALID_ARGUMENT (start_date > end_date).
        """
        with db_session() as db:
            return fetch_transactions(
                db,
                user_id,
                start_date=start_date,
                end_date=end_date,
                symbols=symbols,
                asset_class=asset_class,
            ).model_dump(mode="json")

    @mcp.tool(name="get_benchmark_comparison")
    @tool_handler()
    def get_benchmark_comparison(
        user_id: UUID, window: TimeWindow = TimeWindow.M3
    ) -> dict[str, Any]:
        """Portföyün dönem getirisini BIST 100, altın ve dolarla karşılaştırır.

        Ne zaman kullanılır: "portföyüm borsayı yendi mi", "altın alsaydım daha
        iyi olur muydu", "endekse göre nasıl gidiyorum" gibi kıyaslama
        soruları.

        Ne zaman kullanılmaz: portföyün kendi getirisi tek başına soruluyorsa
        (get_portfolio_performance), varlık bazlı kâr soruluyorsa
        (get_holdings), güncel durum soruluyorsa (get_portfolio_summary),
        bir varlığın fiyat grafiği isteniyorsa (get_asset_price_history).

        Args:
            user_id: Kullanıcının UUID'si.
            window: Kıyaslama penceresi: 1m, 3m, 6m, 12m. Varsayılan 3m.

        Returns:
            Başarılı: data.portfolio_return_percent, data.benchmarks =
            [{symbol, name, return_percent}], data.by_asset_class.
            Getiri, pencere başındaki miktarlar sabit tutularak yalnızca fiyat
            değişiminden hesaplanır; pencere içi alım/satım ve temettü dahil
            değildir — endekslerle aynı ölçekte olması için. Pencere başında
            fiyatı olmayan varlıklar excluded_symbols ile bildirilir.
            Hata: NOT_FOUND · INSUFFICIENT_DATA.
        """
        with db_session() as db:
            return fetch_benchmark(db, user_id, window).model_dump(mode="json")

    return [
        "get_portfolio_summary",
        "get_holdings",
        "get_portfolio_performance",
        "get_transactions",
        "get_benchmark_comparison",
    ]
