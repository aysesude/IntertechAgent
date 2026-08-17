"""Risk değerlendirmesi ve yeniden dengeleme önerisiyle ilgili tüm hesaplama
ve SQL sorguları burada. API katmanı ve MCP tool'ları bu modülü çağırır.

Bu modül risk metodolojisinin *uygulaması*dır, *tanımı* değil: bütün eşikler,
ağırlıklar ve hedef dağılımlar `app/core/config.py`'de yaşar. Buradaki hiçbir
karşılaştırmada sabit sayı yoktur — analistler metodolojiyi bu dosyaya
dokunmadan kalibre edebilir.

Volatilite/korelasyon/kovaryans/VaR/Sharpe, kullanıcının *bugünkü* varlık
ağırlıkları geçmiş fiyat serisine uygulanarak hesaplanır ("mevcut ağırlıkla
geriye dönük bakış"). Bu, portföyün geçmişteki gerçek getirisi değildir —
bugünkü portföyün geçmiş piyasa koşullarında nasıl dalgalanacağının ölçüsüdür.

Döviz cinsinden varlıklar (AK 5.7 ile aynı ilke): her günün değeri O GÜNÜN kur
kapanışıyla TRY'ye çevrilir (bugünkü kurla değil) — aksi halde döviz
varlıkların volatilitesi kur hareketini hiç yansıtmaz."""

import logging
import math
import statistics
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import (
    ASSET_CLASS_BASE_RISK_SCORE,
    RISK_PROFILE_TARGET_ALLOCATION,
    AssetClass,
    RiskLevel,
    RiskProfile,
    settings,
)
from app.core.exceptions import NotFoundError
from app.models import Asset, Holding, Portfolio, PriceHistory, User
from app.providers.tcmb import TcmbEvdsProvider
from app.schemas.risk import (
    CorrelationPair,
    RebalanceAction,
    RebalanceActionType,
    RiskAssessment,
    RiskMetrics,
    RiskProfileSource,
)
from app.services.ledger_service import cash_balance_as_of
from app.services.valuation_service import FX_SYMBOL_BY_CURRENCY, PriceBook

_TWO_DECIMALS = Decimal("0.01")
# HHI 0-1 aralığında olduğu için iki ondalık ayırt edici değil (0.08 ile 0.12
# arasındaki fark çeşitlendirmede büyük fark demek); dört ondalıkla tutuluyor.
_FOUR_DECIMALS = Decimal("0.0001")
_ZERO = Decimal(0)

_logger = logging.getLogger(__name__)

_EMPTY_PORTFOLIO_WARNING = (
    "Portföyünüzde varlık bulunmadığı için risk değerlendirmesi yapılamadı."
)


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_TWO_DECIMALS, rounding=ROUND_HALF_UP)


def _round4(value: Decimal) -> Decimal:
    return value.quantize(_FOUR_DECIMALS, rounding=ROUND_HALF_UP)


def _insufficient_history_warning(available: int) -> str:
    return (
        f"Volatilite, korelasyon, VaR ve Sharpe oranı hesaplanamadı: en az "
        f"{settings.risk_min_price_points} günlük ortak fiyat geçmişi gerekiyor, "
        f"{available} gün mevcut (AK 2.7). Risk skoru kalan ölçütlerle hesaplandı."
    )


def _linear_score(value: float, low: float, high: float) -> float:
    """`low` değerini 0, `high` değerini 100 puana eşleyip arasını doğrusal
    ölçekler; aralık dışını kırpar.

    `low > high` olabilir: çeşitlendirme gibi "değer arttıkça risk azalan"
    ölçütlerde eşikler ters sırada verilir ve formül kendiliğinden tersine döner.
    """
    if high == low:
        return 0.0
    ratio = (value - low) / (high - low)
    return max(0.0, min(1.0, ratio)) * 100.0


def _risk_level(score: float) -> RiskLevel:
    if score <= settings.risk_score_low_max:
        return RiskLevel.LOW
    if score <= settings.risk_score_medium_max:
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


def _inverse_normal_cdf(p: float) -> float:
    """Standart normal dağılımın ters kümülatif dağılım fonksiyonu (z-skoru).

    Peter Acklam'ın rasyonel yaklaşıklığı (scipy bağımlılığı eklememek için) —
    hesaplama hataları ~1.15e-9'dan küçüktür, VaR için fazlasıyla yeterli
    hassasiyettedir."""
    if not 0.0 < p < 1.0:
        raise ValueError("p (0, 1) aralığında olmalı")

    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]

    p_low = 0.02425
    p_high = 1 - p_low

    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
        ) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
    )


def _resolve_risk_free_rate() -> tuple[float, bool]:
    """Sharpe oranı için risksiz getiri oranı (yıllık, oran — 0.37 = %37).

    Önce TCMB EVDS'ten canlı çekmeyi dener (seri kodu ve API anahtarı
    tanımlıysa); herhangi bir sebeple başarısız olursa (anahtar yok, seri
    tanımsız, ağ hatası, beklenmeyen yanıt) sessizce çökmek yerine config'deki
    sabit yedek orana düşer — dış kaynak hatasında zarif düşüş ilkesi
    (CLAUDE.md §4). İkinci değer, oranın canlı mı yedek mi olduğunu belirtir."""
    if settings.risk_free_rate_evds_series and settings.evds_api_key:
        try:
            provider = TcmbEvdsProvider(settings.evds_api_key)
            point = provider.fetch_latest(settings.risk_free_rate_evds_series)
            if point is not None:
                return float(point.close_price) / 100.0, True
        except Exception:  # noqa: BLE001 - dış kaynak asla akışı kesmemeli
            _logger.warning(
                "TCMB EVDS'ten risksiz oran çekilemedi, yedek orana düşülüyor (seri=%s)",
                settings.risk_free_rate_evds_series,
                exc_info=True,
            )
    return settings.risk_free_rate_fallback_annual, False


def _price_series_by_asset(db: Session, asset_ids: list[UUID]) -> dict[UUID, dict[date, Decimal]]:
    """Verilen varlıkların (kendi para biriminde) tüm fiyat geçmişini tek
    sorguda çeker. Kasıtlı olarak carry-forward YAPMAZ: volatilite/korelasyon
    hesabı yalnızca varlığın gerçekten fiyatlandığı günleri kullanmalı,
    aksi halde durağan (taşınmış) günler sahte "getiri sıfır" üretir."""
    if not asset_ids:
        return {}

    rows = db.execute(
        select(PriceHistory.asset_id, PriceHistory.price_date, PriceHistory.close_price)
        .where(PriceHistory.asset_id.in_(asset_ids))
        .order_by(PriceHistory.price_date)
    ).all()

    series: dict[UUID, dict[date, Decimal]] = {}
    for asset_id, price_date, close_price in rows:
        series.setdefault(asset_id, {})[price_date] = close_price
    return series


def _try_convert(
    native_price: Decimal,
    currency: str,
    day: date,
    fx_book: PriceBook,
    fx_asset_id: UUID | None,
) -> Decimal | None:
    """Bir varlığın belirli bir gündeki fiyatını TRY'ye çevirir. Kur bilinmiyorsa
    None döner — eksik veri varsayılarak tamamlanmaz (AK 5.5)."""
    if currency == "TRY":
        return native_price
    if fx_asset_id is None:
        return None
    fx_rate = fx_book.price_at(fx_asset_id, day)
    return None if fx_rate is None else native_price * fx_rate


def _daily_returns(values: list[Decimal]) -> list[float]:
    return [
        float(current) / float(previous) - 1.0
        for previous, current in pairwise(values)
        if previous > 0
    ]


def _annualized_volatility(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(settings.risk_trading_days_per_year)


def _annualized_mean_return(returns: list[float]) -> float | None:
    if not returns:
        return None
    return statistics.mean(returns) * settings.risk_trading_days_per_year


def _max_drawdown(values: list[Decimal]) -> float | None:
    """En yüksek tepe noktasından sonraki en derin düşüşü oran olarak döner
    (0.25 = %25 kayıp). Pozitif bir sayıdır."""
    if not values:
        return None
    peak = _ZERO
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, float(value / peak) - 1.0)
    return abs(worst)


def _pearson_correlation(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 2:
        return None
    try:
        mean_a, mean_b = statistics.mean(a), statistics.mean(b)
        cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / (len(a) - 1)
        std_a, std_b = statistics.stdev(a), statistics.stdev(b)
        if std_a == 0 or std_b == 0:
            return None
        return max(-1.0, min(1.0, cov / (std_a * std_b)))
    except statistics.StatisticsError:
        return None


def _composite_score(
    volatility: float | None,
    max_asset_weight: float,
    effective_holdings: float,
    asset_class_risk_score: float,
) -> float:
    """Dört bileşenin ağırlıklı ortalaması (0-100): volatilite, yoğunlaşma,
    çeşitlendirme, varlık sınıfı bazlı temel risk.

    Volatilite hesaplanamadıysa (AK 2.7) o bileşen atılır ve kalan ağırlıklar
    yeniden normalize edilir — eksik veriyi 0 puan sayıp riski olduğundan
    düşük göstermemek için."""
    components: list[tuple[float, float]] = [
        (
            settings.risk_weight_concentration,
            _linear_score(
                max_asset_weight, settings.risk_concentration_low, settings.risk_concentration_high
            ),
        ),
        (
            settings.risk_weight_diversification,
            _linear_score(
                effective_holdings,
                settings.risk_effective_holdings_low,
                settings.risk_effective_holdings_high,
            ),
        ),
        (settings.risk_weight_asset_class, asset_class_risk_score),
    ]
    if volatility is not None:
        components.append(
            (
                settings.risk_weight_volatility,
                _linear_score(
                    volatility, settings.risk_volatility_low, settings.risk_volatility_high
                ),
            )
        )

    total_weight = sum(weight for weight, _ in components)
    if total_weight <= 0:
        return 0.0
    return sum(weight * score for weight, score in components) / total_weight


def _rebalance_actions(
    profile: RiskProfile, class_values: dict[AssetClass, Decimal], total_value: Decimal
) -> list[RebalanceAction]:
    """Hedef dağılımla mevcut dağılımı karşılaştırır.

    Portföyde hiç bulunmayan varlık sınıfları da (mevcut %0 ile) listelenir —
    eksik bir sınıf, fazla olan bir sınıf kadar anlamlı bir dengesizliktir."""
    targets = RISK_PROFILE_TARGET_ALLOCATION[profile]
    tolerance = Decimal(str(settings.risk_rebalance_tolerance_percent))

    actions: list[RebalanceAction] = []
    for asset_class in settings.supported_asset_classes:
        current_percent = (
            class_values.get(asset_class, _ZERO) / total_value * 100 if total_value > 0 else _ZERO
        )
        target_percent = targets.get(asset_class, _ZERO)
        delta_percent = target_percent - current_percent

        if abs(delta_percent) <= tolerance:
            action = RebalanceActionType.HOLD
        elif delta_percent > 0:
            action = RebalanceActionType.BUY
        else:
            action = RebalanceActionType.SELL

        actions.append(
            RebalanceAction(
                asset_class=asset_class,
                current_percent=_round2(current_percent),
                target_percent=_round2(target_percent),
                delta_percent=_round2(delta_percent),
                delta_amount=_round2(delta_percent / 100 * total_value),
                action=action,
            )
        )
    return actions


def _empty_assessment(
    user_id: UUID,
    profile: RiskProfile,
    source: RiskProfileSource,
    risk_free_rate: float,
    rf_is_live: bool,
) -> RiskAssessment:
    """Boş portföy: çökmek veya sıfır risk iddia etmek yerine nötr bir sonuç
    ve açık bir uyarı döner (CLAUDE.md §4)."""
    return RiskAssessment(
        user_id=user_id,
        as_of=date.today(),
        risk_profile=profile,
        risk_profile_source=source,
        total_value=_ZERO,
        risk_score=None,
        risk_level=None,
        metrics=RiskMetrics(
            annualized_volatility_percent=None,
            max_drawdown_percent=None,
            covariance_volatility_percent=None,
            correlation_matrix=[],
            value_at_risk_try=None,
            value_at_risk_percent=None,
            value_at_risk_confidence=_round2(Decimal(str(settings.risk_var_confidence * 100))),
            value_at_risk_horizon_days=settings.risk_var_horizon_days,
            sharpe_ratio=None,
            risk_free_rate_percent=_round2(Decimal(str(risk_free_rate * 100))),
            risk_free_rate_is_live=rf_is_live,
            max_asset_weight_percent=_ZERO,
            max_asset_symbol=None,
            max_class_weight_percent=_ZERO,
            max_class=None,
            herfindahl_index=_ZERO,
            effective_holdings_count=_ZERO,
            asset_class_base_risk_score=_ZERO,
            holdings_count=0,
            asset_class_count=0,
            price_points_used=0,
        ),
        rebalance_actions=[],
        is_balanced=False,
        warnings=[_EMPTY_PORTFOLIO_WARNING],
    )


def get_risk_assessment(
    db: Session, user_id: UUID, profile_override: RiskProfile | None = None
) -> RiskAssessment:
    """Kullanıcının portföy riskini değerlendirir ve yeniden dengeleme önerir.

    `profile_override` verilirse hesaplama o profile göre yapılır ama
    kullanıcının DB'deki kalıcı profili değişmez — "ya agresif olsaydım?"
    senaryosu için."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User not found for user_id {user_id}")

    profile = profile_override or user.risk_profile
    source = RiskProfileSource.OVERRIDE if profile_override is not None else RiskProfileSource.USER

    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    holdings = (
        db.execute(
            select(Holding)
            .where(Holding.portfolio_id == portfolio.id, Holding.quantity > 0)
            .options(joinedload(Holding.asset))
        )
        .scalars()
        .all()
    )

    risk_free_rate, rf_is_live = _resolve_risk_free_rate()

    if not holdings:
        return _empty_assessment(user_id, profile, source, risk_free_rate, rf_is_live)

    asset_ids = [h.asset_id for h in holdings]
    currency_by_asset = {h.asset_id: h.asset.currency for h in holdings}
    foreign_currencies = {c for c in currency_by_asset.values() if c != "TRY"}

    # --- Kur defteri (carry-forward destekli) ---
    fx_ids: dict[str, UUID] = {}
    fx_book = PriceBook([])
    if foreign_currencies:
        fx_symbols = {
            currency: FX_SYMBOL_BY_CURRENCY[currency]
            for currency in foreign_currencies
            if currency in FX_SYMBOL_BY_CURRENCY
        }
        fx_asset_rows = db.execute(
            select(Asset.id, Asset.symbol).where(Asset.symbol.in_(fx_symbols.values()))
        ).all()
        symbol_to_id = {symbol: aid for aid, symbol in fx_asset_rows}
        for currency, symbol in fx_symbols.items():
            if symbol in symbol_to_id:
                fx_ids[currency] = symbol_to_id[symbol]

        fx_rows = db.execute(
            select(PriceHistory.asset_id, PriceHistory.price_date, PriceHistory.close_price).where(
                PriceHistory.asset_id.in_(fx_ids.values())
            )
        ).all()
        fx_book = PriceBook([(r.asset_id, r.price_date, r.close_price) for r in fx_rows])

    # --- Ham (kendi para biriminde) fiyat geçmişi + TRY'ye çevrilmiş seri ---
    raw_series = _price_series_by_asset(db, asset_ids)
    try_series: dict[UUID, dict[date, Decimal]] = {}
    for asset_id, native_by_date in raw_series.items():
        currency = currency_by_asset[asset_id]
        fx_asset_id = fx_ids.get(currency)
        converted: dict[date, Decimal] = {}
        for day, native_price in native_by_date.items():
            try_price = _try_convert(native_price, currency, day, fx_book, fx_asset_id)
            if try_price is not None:
                converted[day] = try_price
        try_series[asset_id] = converted

    # --- Bugünkü değer ve ağırlıklar ---
    symbol_by_asset_id = {h.asset_id: h.asset.symbol for h in holdings}
    market_values: dict[UUID, Decimal] = {}
    class_values: dict[AssetClass, Decimal] = {}
    class_by_asset_id: dict[UUID, AssetClass] = {}
    as_of_dates: list[date] = []

    for holding in holdings:
        prices = try_series.get(holding.asset_id, {})
        if prices:
            latest_date = max(prices)
            price = prices[latest_date]
            as_of_dates.append(latest_date)
        else:
            # Fiyat geçmişi hiç yoksa maliyet fiyatına düşülür — portfolio_service
            # ile aynı davranış, tutarlı toplam değer için.
            price = holding.avg_cost_price

        value = holding.quantity * price
        market_values[holding.asset_id] = value
        class_by_asset_id[holding.asset_id] = holding.asset.asset_class
        class_values[holding.asset.asset_class] = (
            class_values.get(holding.asset.asset_class, _ZERO) + value
        )

    # Serbest nakit (defterden): toplam değere ve CASH dilimine eklenir —
    # portfolio_service ile aynı ilke, aksi halde yeniden dengeleme önerisi
    # nakdi hiç görmez ve CASH hedefini her zaman "tamamen eksik" sanır.
    asset_only_total = sum(market_values.values(), start=_ZERO)
    cash_balance = cash_balance_as_of(db, portfolio.id)
    total_value = asset_only_total + cash_balance
    if cash_balance != 0:
        class_values[AssetClass.CASH] = class_values.get(AssetClass.CASH, _ZERO) + cash_balance

    if total_value <= 0:
        return _empty_assessment(user_id, profile, source, risk_free_rate, rf_is_live)

    # Yoğunlaşma/çeşitlendirme ağırlıkları yalnızca yatırılan varlıklar
    # üzerinden hesaplanır (nakit kasıtlı olarak dışarıda tutulur — sabit,
    # risksiz bir pozisyonun "çeşitlendirme" gibi görünmesi yanıltıcı olur).
    weights = (
        {asset_id: value / asset_only_total for asset_id, value in market_values.items()}
        if asset_only_total > 0
        else {asset_id: _ZERO for asset_id in market_values}
    )

    # --- Yoğunlaşma ve çeşitlendirme ---
    top_asset_id = max(weights, key=lambda aid: weights[aid])
    max_asset_weight = weights[top_asset_id]

    top_class = max(class_values, key=lambda ac: class_values[ac])
    max_class_weight = class_values[top_class] / total_value

    herfindahl = sum((w * w for w in weights.values()), start=_ZERO)
    effective_holdings = Decimal(1) / herfindahl if herfindahl > 0 else _ZERO

    # --- Varlık sınıfı bazlı temel risk (BR: hisse=yüksek, tahvil=düşük vb.) ---
    asset_class_risk_score = float(
        sum(
            (weights[aid] * ASSET_CLASS_BASE_RISK_SCORE.get(class_by_asset_id[aid], _ZERO))
            for aid in weights
        )
    )

    # --- Ortak fiyat günleri (tüm elde tutulan varlıkların TRY fiyatının
    # bilindiği günler) ---
    common_dates: set[date] | None = None
    for asset_id in asset_ids:
        dates = set(try_series.get(asset_id, {}))
        common_dates = dates if common_dates is None else common_dates & dates
        if not common_dates:
            common_dates = set()
            break
    sorted_dates = sorted(common_dates or ())
    price_points = len(sorted_dates)

    warnings: list[str] = []
    volatility = drawdown = covariance_vol = portfolio_return = None
    sharpe = var_try = var_percent = None
    correlation_pairs: list[CorrelationPair] = []

    if price_points >= settings.risk_min_price_points:
        # Portföy değer serisi (bugünkü miktarlarla).
        value_series = [
            sum((h.quantity * try_series[h.asset_id][day] for h in holdings), start=_ZERO)
            for day in sorted_dates
        ]
        portfolio_returns = _daily_returns(value_series)
        volatility = _annualized_volatility(portfolio_returns)
        drawdown = _max_drawdown(value_series)

        # Varlık başına günlük getiri serileri (ortak günler üzerinden).
        returns_by_asset: dict[UUID, list[float]] = {
            asset_id: _daily_returns([try_series[asset_id][day] for day in sorted_dates])
            for asset_id in asset_ids
        }

        # Korelasyon matrisi (yalnızca farklı varlık çiftleri, tek yönlü).
        ordered_ids = list(asset_ids)
        for i, a_id in enumerate(ordered_ids):
            for b_id in ordered_ids[i + 1 :]:
                corr = _pearson_correlation(returns_by_asset[a_id], returns_by_asset[b_id])
                if corr is not None:
                    correlation_pairs.append(
                        CorrelationPair(
                            asset_symbol_a=symbol_by_asset_id[a_id],
                            asset_symbol_b=symbol_by_asset_id[b_id],
                            correlation=_round4(Decimal(str(corr))),
                        )
                    )

        # Kovaryans tabanlı yıllık portföy volatilitesi (AK 2.3): w^T * Sigma * w.
        vols_by_asset = {
            aid: _annualized_volatility(returns_by_asset[aid]) for aid in ordered_ids
        }
        if all(v is not None for v in vols_by_asset.values()):
            variance = 0.0
            for a_id in ordered_ids:
                for b_id in ordered_ids:
                    if a_id == b_id:
                        corr_ab = 1.0
                    else:
                        corr_ab = _pearson_correlation(
                            returns_by_asset[a_id], returns_by_asset[b_id]
                        )
                        if corr_ab is None:
                            corr_ab = 0.0
                    variance += (
                        float(weights[a_id])
                        * float(weights[b_id])
                        * vols_by_asset[a_id]
                        * vols_by_asset[b_id]
                        * corr_ab
                    )
            covariance_vol = math.sqrt(max(0.0, variance))

        # Portföy beklenen getirisi (yıllık) — aynı veri setinden, Sharpe için.
        mean_returns = {aid: _annualized_mean_return(returns_by_asset[aid]) for aid in ordered_ids}
        if all(v is not None for v in mean_returns.values()):
            portfolio_return = sum(
                float(weights[aid]) * mean_returns[aid] for aid in ordered_ids
            )

        # VaR (parametrik, AK 2.4): kovaryans tabanlı volatilite varsa onu,
        # yoksa doğrudan portföy değer serisinden hesaplanan volatiliteyi kullanır.
        var_source_vol = covariance_vol if covariance_vol is not None else volatility
        if var_source_vol is not None:
            z = _inverse_normal_cdf(settings.risk_var_confidence)
            daily_vol = var_source_vol / math.sqrt(settings.risk_trading_days_per_year)
            horizon_vol = daily_vol * math.sqrt(settings.risk_var_horizon_days)
            var_ratio = z * horizon_vol
            var_percent = Decimal(str(var_ratio * 100))
            var_try = Decimal(str(var_ratio)) * total_value

        # Sharpe oranı (AK 2.5).
        sharpe_source_vol = covariance_vol if covariance_vol is not None else volatility
        if portfolio_return is not None and sharpe_source_vol not in (None, 0):
            sharpe = (portfolio_return - risk_free_rate) / sharpe_source_vol
    else:
        warnings.append(_insufficient_history_warning(price_points))

    score = _composite_score(
        volatility, float(max_asset_weight), float(effective_holdings), asset_class_risk_score
    )
    actions = _rebalance_actions(profile, class_values, total_value)

    return RiskAssessment(
        user_id=user_id,
        as_of=max(as_of_dates) if as_of_dates else date.today(),
        risk_profile=profile,
        risk_profile_source=source,
        total_value=_round2(total_value),
        risk_score=_round2(Decimal(str(score))),
        risk_level=_risk_level(score),
        metrics=RiskMetrics(
            annualized_volatility_percent=(
                _round2(Decimal(str(volatility * 100))) if volatility is not None else None
            ),
            max_drawdown_percent=(
                _round2(Decimal(str(drawdown * 100))) if drawdown is not None else None
            ),
            covariance_volatility_percent=(
                _round2(Decimal(str(covariance_vol * 100))) if covariance_vol is not None else None
            ),
            correlation_matrix=correlation_pairs,
            value_at_risk_try=_round2(var_try) if var_try is not None else None,
            value_at_risk_percent=_round2(var_percent) if var_percent is not None else None,
            value_at_risk_confidence=_round2(Decimal(str(settings.risk_var_confidence * 100))),
            value_at_risk_horizon_days=settings.risk_var_horizon_days,
            sharpe_ratio=_round2(Decimal(str(sharpe))) if sharpe is not None else None,
            risk_free_rate_percent=_round2(Decimal(str(risk_free_rate * 100))),
            risk_free_rate_is_live=rf_is_live,
            max_asset_weight_percent=_round2(max_asset_weight * 100),
            max_asset_symbol=symbol_by_asset_id[top_asset_id],
            max_class_weight_percent=_round2(max_class_weight * 100),
            max_class=top_class,
            herfindahl_index=_round4(herfindahl),
            effective_holdings_count=_round2(effective_holdings),
            asset_class_base_risk_score=_round2(Decimal(str(asset_class_risk_score))),
            holdings_count=len(holdings),
            asset_class_count=len(class_values),
            price_points_used=price_points,
        ),
        rebalance_actions=actions,
        is_balanced=all(a.action == RebalanceActionType.HOLD for a in actions),
        warnings=warnings,
    )
