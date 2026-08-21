"""Risk değerlendirmesi ve yeniden dengeleme önerisiyle ilgili tüm hesaplama
ve SQL sorguları burada. API katmanı ve MCP tool'ları bu modülü çağırır.

Bu modül risk metodolojisinin *uygulaması*dır, *tanımı* değil: bütün eşikler,
ağırlıklar ve hedef dağılımlar `app/core/config.py`'de yaşar. Buradaki hiçbir
karşılaştırmada sabit sayı yoktur — analistler metodolojiyi bu dosyaya
dokunmadan kalibre edebilir.

v2 (Risk/Strateji Ajanı analist belgesi, Google Doc "Intertech - Ekip 3"):
volatilite/korelasyon artık VARLIK değil KATEGORİ bazlıdır (Hisse/Altın/
Döviz/Tahvil/Nakit — sabit 5x5 matris). Bir kategorinin günlük getirisi,
o kategorideki varlıkların BUGÜNKÜ TL ağırlıklı ortalamasıdır (u_i=V_i/V_k) —
"bugünkü portföyün geçmiş piyasa koşullarında nasıl dalgalanacağı" ilkesiyle
tutarlı, portföyün geçmişteki gerçek getirisi değildir. Risk seviyesi artık
yalnızca yıllık portföy volatilitesinden gelen 7 kademeli bir etikettir; eski
0-100 kompozit `risk_score` tamamen kaldırıldı. Yerini `RiskCauseDiagnosis`
(risk neden yüksek çıktı — yalnızca kullanıcının profili için beklenen bandın
üzerindeyken hesaplanır) ve `RebalanceScenario` (kural tabanlı, deterministik
Aksiyon A/B/C simülasyonu) aldı.

Döviz cinsinden varlıklar (AK 5.7 ile aynı ilke): her günün değeri O GÜNÜN kur
kapanışıyla TRY'ye çevrilir (bugünkü kurla değil) — aksi halde döviz
varlıkların volatilitesi kur hareketini hiç yansıtmaz.

Kapsam sınırlaması (bilinçli tasarım kararı, bkz. `_select_receiver`): AK-5/
AK-6 — o an portföyde hiç bulunmayan (ağırlığı sıfır) bir kategorinin
senaryoda "açılması" — uygulanmadı. O kategori için geçmiş volatilite/
korelasyon verisi yok, dolayısıyla hangi transferin riski gerçekten
azaltacağı hesaplanamaz. Desteklenmesi istenirse varsayılan bir kategori
volatilite tablosu gerekir."""

import logging
import math
import statistics
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations, pairwise
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import (
    RISK_DEFENSE_FLOOR,
    RISK_LEVEL_VOLATILITY_UPPER_BOUNDS,
    RISK_MAX_ASSET_WEIGHT,
    RISK_MAX_CATEGORY_WEIGHT,
    RISK_RECEIVER_PREFERENCE_ORDER,
    RISK_TARGET_VOLATILITY_BAND,
    AssetClass,
    RiskLevel,
    RiskProfile,
    settings,
)
from app.core.exceptions import NotFoundError
from app.models import Asset, Holding, Portfolio, PriceHistory, User
from app.providers.tcmb import TcmbEvdsProvider
from app.schemas.risk import (
    CategoryCorrelationPair,
    CategoryMetrics,
    ConcentrationCause,
    CorrelationCause,
    HighVolatilityAssetCause,
    RebalanceScenario,
    RiskAssessment,
    RiskCauseDiagnosis,
    RiskMetrics,
    RiskProfileSource,
    ScenarioAssetWeight,
    ScenarioCategoryWeight,
)
from app.services.ledger_service import cash_balance_as_of
from app.services.valuation_service import FX_SYMBOL_BY_CURRENCY, PriceBook

_TWO_DECIMALS = Decimal("0.01")
# HHI ve korelasyon 0-1 aralığında olduğu için iki ondalık ayırt edici değil
# (0.08 ile 0.12 arasındaki fark çeşitlendirmede büyük fark demek); dört
# ondalıkla tutuluyor.
_FOUR_DECIMALS = Decimal("0.0001")
_ZERO = Decimal(0)

_logger = logging.getLogger(__name__)

_EMPTY_PORTFOLIO_WARNING = "Portföyünüzde varlık bulunmadığı için risk değerlendirmesi yapılamadı."

# Aksiyonların KK-1 gereği her zaman uygulandığı sabit sıra.
_ACTION_KEYS = ["A", "B", "C"]


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_TWO_DECIMALS, rounding=ROUND_HALF_UP)


def _round4(value: Decimal) -> Decimal:
    return value.quantize(_FOUR_DECIMALS, rounding=ROUND_HALF_UP)


def _insufficient_history_warning(available: int) -> str:
    return (
        f"Risk seviyesi hesaplanamadı: en az {settings.risk_min_price_points} günlük ortak "
        f"fiyat geçmişi gerekiyor, {available} gün mevcut (AK 2.7). Risk uydurulmaz."
    )


def _missing_category_data_warning() -> str:
    return (
        "Portföy volatilitesi hesaplanamadı: elde tutulan kategorilerden en az birinin "
        "yıllık volatilitesi yeterli fiyat verisiyle hesaplanamadı (AK 2.7). Risk seviyesi "
        "bu nedenle gösterilemiyor."
    )


def _inverse_normal_cdf(p: float) -> float:
    """Standart normal dağılımın ters kümülatif dağılım fonksiyonu (z-skoru).

    Peter Acklam'ın rasyonel yaklaşıklığı (scipy bağımlılığı eklememek için) —
    hesaplama hataları ~1.15e-9'dan küçüktür, VaR için fazlasıyla yeterli
    hassasiyettedir."""
    if not 0.0 < p < 1.0:
        raise ValueError("p (0, 1) aralığında olmalı")

    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]

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
        return ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) / (
            ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1
        )
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


def _returns_aligned(values: list[Decimal]) -> list[float]:
    """`_daily_returns` gibi ama hizalıdır: `previous<=0` gibi (gerçek piyasa
    verisinde neredeyse hiç olmayan) bir durumda o günü ATLAMAZ, 0.0 getiri
    yazar. Kategori getirisini varlık bazında ağırlıklı toplarken tüm
    serilerin aynı uzunlukta ve aynı gün indeksinde kalması gerekiyor."""
    return [
        float(current) / float(previous) - 1.0 if previous > 0 else 0.0
        for previous, current in pairwise(values)
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


def _risk_level_from_volatility(volatility: float) -> RiskLevel:
    """Yıllık portföy volatilitesinden 7 kademeli risk etiketi. Son sınırın
    (0.40) üzerindeki her volatilite VERY_HIGH sayılır."""
    vol_decimal = Decimal(str(volatility))
    for upper_bound, level in RISK_LEVEL_VOLATILITY_UPPER_BOUNDS:
        if vol_decimal <= upper_bound:
            return level
    return RiskLevel.VERY_HIGH


# --------------------------------------------------------------------------
# Kategori bazlı volatilite/korelasyon
# --------------------------------------------------------------------------


def _category_returns(
    class_values: dict[AssetClass, Decimal],
    asset_ids_by_class: dict[AssetClass, list[UUID]],
    try_series: dict[UUID, dict[date, Decimal]],
    market_values: dict[UUID, Decimal],
    sorted_dates: list[date],
) -> dict[AssetClass, list[float]]:
    """Her kategori için ortak günler üzerinden günlük getiri serisi.

    Kategori getirisi, o kategorideki varlıkların BUGÜNKÜ TL değer ağırlıklı
    ortalamasıdır (u_i=V_i/V_kategori) — geçmişteki ağırlık değil, "bugünkü
    portföy geçmiş koşullarda nasıl dalgalanır" ilkesiyle tutarlı. Serbest
    nakit (ledger'dan) kategori DEĞERİNE dahildir ama fiyatlanan bir varlık
    olmadığı için getiri serisine katkısı sıfırdır — bu da kategorinin
    volatilitesini doğal biçimde seyreltir, ayrı bir "sıfır getirili satır"
    icat etmeye gerek kalmaz. Yalnızca serbest nakitten oluşan (hiç fiyatlı
    varlığı olmayan) bir kategori tamamen sıfır getirili bir seri alır —
    doğru sonuç, nakit zaten volatil değildir."""
    n_returns = max(len(sorted_dates) - 1, 0)
    category_returns: dict[AssetClass, list[float]] = {}
    for asset_class, category_value in class_values.items():
        if category_value <= 0:
            continue
        weighted_daily = [0.0] * n_returns
        for asset_id in asset_ids_by_class.get(asset_class, []):
            weight = float(market_values[asset_id] / category_value)
            if weight <= 0:
                continue
            asset_values = [try_series[asset_id][day] for day in sorted_dates]
            asset_returns = _returns_aligned(asset_values)
            for i, r in enumerate(asset_returns):
                weighted_daily[i] += weight * r
        category_returns[asset_class] = weighted_daily
    return category_returns


def _category_correlation_matrix(
    category_returns: dict[AssetClass, list[float]],
) -> dict[tuple[AssetClass, AssetClass], float]:
    """Sabit 5x5 matrisin üst üçgeni (i<j, AssetClass tanım sırasıyla).
    Hesaplanamayan çiftler (örn. sabit/sıfır getirili nakit serisiyle
    stdev=0 olan bir seri) sözlükte yer almaz."""
    pairs: dict[tuple[AssetClass, AssetClass], float] = {}
    classes = [ac for ac in AssetClass if ac in category_returns]
    for i, a in enumerate(classes):
        for b in classes[i + 1 :]:
            corr = _pearson_correlation(category_returns[a], category_returns[b])
            if corr is not None:
                pairs[(a, b)] = corr
    return pairs


def _correlation_between(
    a: AssetClass, b: AssetClass, correlations: dict[tuple[AssetClass, AssetClass], float]
) -> float:
    if a == b:
        return 1.0
    corr = correlations.get((a, b))
    if corr is None:
        corr = correlations.get((b, a))
    return corr if corr is not None else 0.0


def _portfolio_volatility_from_categories(
    category_weights: dict[AssetClass, Decimal],
    category_vols: dict[AssetClass, float | None],
    correlations: dict[tuple[AssetClass, AssetClass], float],
) -> float | None:
    """σ_portföy = sqrt(ΣᵢΣⱼ wᵢwⱼρᵢⱼσᵢσⱼ). Ağırlığı pozitif olan bir
    kategorinin volatilitesi hesaplanamıyorsa (AK 2.7) portföy volatilitesi
    de None döner — uydurulmaz."""
    classes = [ac for ac in category_weights if category_weights[ac] > 0]
    if not classes or any(category_vols.get(ac) is None for ac in classes):
        return None
    variance = 0.0
    for a in classes:
        for b in classes:
            corr = _correlation_between(a, b, correlations)
            variance += (
                float(category_weights[a])
                * float(category_weights[b])
                * category_vols[a]
                * category_vols[b]
                * corr
            )
    return math.sqrt(max(0.0, variance))


def _risk_contributions(
    category_weights: dict[AssetClass, Decimal],
    category_vols: dict[AssetClass, float],
    correlations: dict[tuple[AssetClass, AssetClass], float],
    portfolio_vol: float,
) -> dict[AssetClass, float]:
    """RC%ᵢ = wᵢ·(Σⱼ wⱼσᵢσⱼρᵢⱼ)/σ_portföy² (Euler varyans ayrıştırması,
    Σ RC%ᵢ≈1). Aksiyon B'nin "en yüksek RC%'li kategoriden al" kuralında ve
    kök neden teşhisinde kullanılır."""
    if portfolio_vol <= 0:
        return {}
    classes = [ac for ac in category_weights if category_weights[ac] > 0]
    contributions: dict[AssetClass, float] = {}
    for a in classes:
        marginal = sum(
            float(category_weights[b])
            * category_vols[a]
            * category_vols[b]
            * _correlation_between(a, b, correlations)
            for b in classes
        )
        contributions[a] = float(category_weights[a]) * marginal / (portfolio_vol**2)
    return contributions


def _diversification_ratio(
    category_weights: dict[AssetClass, Decimal],
    category_vols: dict[AssetClass, float],
    portfolio_vol: float,
) -> float | None:
    """DR = (Σ wᵢ×σᵢ) / σ_portföy. 1'e yakınsa çeşitlendirme etkisi zayıf,
    büyüdükçe (>1) çeşitlendirme riski azaltıyor demektir."""
    if portfolio_vol <= 0:
        return None
    weighted_sum = sum(
        float(category_weights[ac]) * category_vols[ac]
        for ac in category_weights
        if category_weights[ac] > 0
    )
    return weighted_sum / portfolio_vol


# --------------------------------------------------------------------------
# Kök neden teşhisi ("risk neden yüksek çıktı")
# --------------------------------------------------------------------------


def _diagnose_causes(
    max_asset_weight: Decimal,
    max_asset_symbol: str | None,
    category_weights: dict[AssetClass, Decimal],
    herfindahl: Decimal,
    asset_vols: dict[UUID, float | None],
    asset_weights: dict[UUID, Decimal],
    risk_contributions: dict[AssetClass, float],
    correlations: dict[tuple[AssetClass, AssetClass], float],
    diversification_ratio: float | None,
) -> RiskCauseDiagnosis:
    """Yalnızca portföy volatilitesi kullanıcının profili için beklenen
    bandın üzerindeyken çağrılır (bkz. get_risk_assessment).

    Rüveyda'nın onayladığı doğru eşleşme (formüller doğru, yalnızca alt
    başlık atamaları yanlıştı — bu session'da netleştirildi):
      Neden A — Yoğunlaşma: max(w_varlık)>eşik VEYA max(w_kategori)>eşik
                VEYA HHI>eşik.
      Neden B — Yüksek volatiliteli varlık: (yıllık vol>eşik olan
                varlıkların toplam ağırlığı)>eşik VEYA (bir kategorinin
                RC%>eşik VE RC%>o kategorinin ağırlığı+eşik).
      Neden C — Korelasyon: (ağırlığı>=%10 olan kategoriler arasındaki en
                yüksek ikili korelasyon>=eşik VE o çiftin toplam
                ağırlığı>=eşik) VEYA (DR<eşik VE HHI<=eşik).
    """
    top_class = max(category_weights, key=lambda ac: category_weights[ac])
    max_category_weight = category_weights[top_class]

    # --- Neden A: Yoğunlaşma ---
    concentration_triggered = (
        float(max_asset_weight) > settings.risk_cause_max_asset_weight
        or float(max_category_weight) > settings.risk_cause_max_category_weight
        or float(herfindahl) > settings.risk_cause_hhi_threshold
    )
    concentration = ConcentrationCause(
        triggered=concentration_triggered,
        max_asset_weight_percent=_round2(max_asset_weight * 100),
        max_asset_symbol=max_asset_symbol,
        max_category_weight_percent=_round2(max_category_weight * 100),
        max_category=top_class,
        herfindahl_index=_round4(herfindahl),
    )

    # --- Neden B: Yüksek volatiliteli varlık ---
    high_vol_weight = sum(
        (
            asset_weights[aid]
            for aid, vol in asset_vols.items()
            if vol is not None and vol > settings.risk_cause_high_vol_asset_annual_vol
        ),
        start=_ZERO,
    )
    max_rc_category = (
        max(risk_contributions, key=lambda ac: risk_contributions[ac])
        if risk_contributions
        else None
    )
    max_rc_percent = (
        risk_contributions.get(max_rc_category) if max_rc_category is not None else None
    )
    rc_condition = False
    if max_rc_category is not None and max_rc_percent is not None:
        rc_condition = (
            max_rc_percent > settings.risk_cause_risk_contribution_threshold
            and max_rc_percent
            > float(category_weights.get(max_rc_category, _ZERO))
            + settings.risk_cause_risk_contribution_excess
        )
    high_vol_triggered = (
        float(high_vol_weight) > settings.risk_cause_high_vol_asset_weight or rc_condition
    )
    high_volatility_asset = HighVolatilityAssetCause(
        triggered=high_vol_triggered,
        high_volatility_assets_weight_percent=_round2(high_vol_weight * 100),
        max_risk_contribution_category=max_rc_category,
        max_risk_contribution_percent=(
            _round2(Decimal(str(max_rc_percent * 100))) if max_rc_percent is not None else None
        ),
    )

    # --- Neden C: Korelasyon ---
    eligible = [ac for ac in category_weights if category_weights[ac] >= Decimal("0.10")]
    best_pair: tuple[AssetClass, AssetClass] | None = None
    best_corr: float | None = None
    for i, a in enumerate(eligible):
        for b in eligible[i + 1 :]:
            corr = correlations.get((a, b))
            if corr is None:
                corr = correlations.get((b, a))
            if corr is None:
                continue
            if best_corr is None or corr > best_corr:
                best_corr, best_pair = corr, (a, b)

    pair_weight_sum = (
        category_weights.get(best_pair[0], _ZERO) + category_weights.get(best_pair[1], _ZERO)
        if best_pair is not None
        else _ZERO
    )
    hhi_low = float(herfindahl) <= settings.risk_cause_hhi_low_threshold
    dr_condition = (
        diversification_ratio is not None
        and diversification_ratio < settings.risk_cause_dr_threshold
        and hhi_low
    )
    corr_pair_condition = (
        best_corr is not None
        and best_corr >= settings.risk_cause_pairwise_correlation
        and float(pair_weight_sum) >= settings.risk_cause_pairwise_weight_sum
    )
    correlation = CorrelationCause(
        triggered=corr_pair_condition or dr_condition,
        highest_correlated_pair=(
            CategoryCorrelationPair(
                category_a=best_pair[0],
                category_b=best_pair[1],
                correlation=_round4(Decimal(str(best_corr))),
            )
            if best_pair is not None and best_corr is not None
            else None
        ),
        diversification_ratio=(
            _round2(Decimal(str(diversification_ratio)))
            if diversification_ratio is not None
            else None
        ),
        herfindahl_index=_round4(herfindahl),
    )

    return RiskCauseDiagnosis(
        concentration=concentration,
        high_volatility_asset=high_volatility_asset,
        correlation=correlation,
    )


# --------------------------------------------------------------------------
# Yeniden dengeleme senaryo motoru (Aksiyon A/B/C)
# --------------------------------------------------------------------------


def _average_correlation(
    category: AssetClass,
    weights: dict[AssetClass, Decimal],
    correlations: dict[tuple[AssetClass, AssetClass], float],
) -> float:
    others = [ac for ac in weights if ac != category and weights[ac] > 0]
    if not others:
        return 0.0
    return sum(_correlation_between(category, other, correlations) for other in others) / len(
        others
    )


def _select_receiver(
    profile: RiskProfile,
    donor: AssetClass,
    weights: dict[AssetClass, Decimal],
    correlations: dict[tuple[AssetClass, AssetClass], float],
) -> AssetClass | None:
    """AK-1..AK-4/AK-7: donor'un ortalama korelasyonu en düşük olan, kendi
    profil limitine henüz ulaşmamış, ZATEN ELDE TUTULAN (ağırlık>0)
    kategoriyi seçer. Korelasyon farkı eşiğin altındaki adaylar arasında
    profilin alıcı tercih sırası (AK-4) belirleyicidir.

    AK-5/AK-6 (sıfır ağırlıklı yeni bir kategori açma) kasıtlı olarak
    uygulanmadı — bkz. modül docstring'i."""
    limits = RISK_MAX_CATEGORY_WEIGHT[profile]
    candidates = [
        (ac, _average_correlation(ac, weights, correlations))
        for ac, weight in weights.items()
        if ac != donor and weight > 0 and weight < limits[ac]
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[1])
    lowest_corr = candidates[0][1]
    tied = [
        ac
        for ac, corr in candidates
        if corr - lowest_corr < settings.risk_scenario_correlation_tie_threshold
    ]
    if len(tied) == 1:
        return tied[0]
    for ac in RISK_RECEIVER_PREFERENCE_ORDER[profile]:
        if ac in tied:
            return ac
    return tied[0]


def _run_transfer_loop(
    profile: RiskProfile,
    weights: dict[AssetClass, Decimal],
    donor: AssetClass,
    correlations: dict[tuple[AssetClass, AssetClass], float],
    should_stop,
    used_turnover: Decimal,
    max_turnover: Decimal,
) -> tuple[dict[AssetClass, Decimal], Decimal]:
    """STEP büyüklüğünde ardışık transferler (KS-1/KS-2: kural tabanlı,
    deterministik). Her adımda: savunma tabanı (Tahvil+Nakit), alıcının
    kategori üst sınırı ve KK-2'nin paylaşılan turnover bütçesi kontrol
    edilir. MAX_ITER, sonsuz döngü emniyet supabıdır."""
    step = Decimal(str(settings.risk_scenario_step_percent)) / 100
    defense_floor = RISK_DEFENSE_FLOOR[profile]
    limits = RISK_MAX_CATEGORY_WEIGHT[profile]
    current = dict(weights)

    for _ in range(settings.risk_scenario_max_iterations):
        if should_stop(current) or used_turnover >= max_turnover:
            break
        if current[donor] <= 0:
            break

        remaining_budget = max_turnover - used_turnover
        if donor in (AssetClass.BOND, AssetClass.CASH):
            defense_total = current.get(AssetClass.BOND, _ZERO) + current.get(
                AssetClass.CASH, _ZERO
            )
            donor_available = max(_ZERO, defense_total - defense_floor)
        else:
            donor_available = current[donor]
        transfer_amount = min(step, current[donor], donor_available, remaining_budget)
        if transfer_amount <= 0:
            break

        receiver = _select_receiver(profile, donor, current, correlations)
        if receiver is None:
            break
        room = limits[receiver] - current.get(receiver, _ZERO)
        if room <= 0:
            break
        transfer_amount = min(transfer_amount, room)
        if transfer_amount <= 0:
            break

        current[donor] -= transfer_amount
        current[receiver] = current.get(receiver, _ZERO) + transfer_amount
        used_turnover += transfer_amount

    return current, used_turnover


def _target_volatility(profile: RiskProfile, current_vol: float) -> float:
    """Aksiyon B'nin durma koşulu: mevcut volatilite profilin hedef bandının
    üst sınırını <=5 puan aşıyorsa hedef=üst sınır, >5 puan aşıyorsa
    hedef=bandın orta noktası."""
    lower, upper = RISK_TARGET_VOLATILITY_BAND[profile]
    upper_f, lower_f = float(upper), float(lower)
    if current_vol - upper_f <= 0.05:
        return upper_f
    return (lower_f + upper_f) / 2


def _highest_correlated_pair(
    weights: dict[AssetClass, Decimal], correlations: dict[tuple[AssetClass, AssetClass], float]
) -> tuple[AssetClass, AssetClass] | None:
    classes = [ac for ac in AssetClass if weights.get(ac, _ZERO) > 0]
    best: tuple[AssetClass, AssetClass] | None = None
    best_corr: float | None = None
    for i, a in enumerate(classes):
        for b in classes[i + 1 :]:
            corr = correlations.get((a, b))
            if corr is None:
                corr = correlations.get((b, a))
            if corr is None:
                continue
            if best_corr is None or corr > best_corr:
                best_corr, best = corr, (a, b)
    return best


def _apply_action_a(
    profile: RiskProfile,
    weights: dict[AssetClass, Decimal],
    category_vols: dict[AssetClass, float],
    correlations: dict[tuple[AssetClass, AssetClass], float],
    used_turnover: Decimal,
    max_turnover: Decimal,
) -> tuple[dict[AssetClass, Decimal], Decimal] | None:
    """Aksiyon A — Yoğunlaşmayı kır: kategori üst sınırını en çok aşan
    kategoriden, limitin altına inene kadar transfer eder. Hiçbir kategori
    limitini aşmıyorsa uygulanamaz (None)."""
    limits = RISK_MAX_CATEGORY_WEIGHT[profile]
    donor = max(weights, key=lambda ac: weights[ac] - limits[ac])
    if weights[donor] <= limits[donor]:
        return None
    return _run_transfer_loop(
        profile,
        weights,
        donor,
        correlations,
        should_stop=lambda w: w[donor] <= limits[donor],
        used_turnover=used_turnover,
        max_turnover=max_turnover,
    )


def _apply_action_b(
    profile: RiskProfile,
    weights: dict[AssetClass, Decimal],
    category_vols: dict[AssetClass, float],
    correlations: dict[tuple[AssetClass, AssetClass], float],
    current_vol: float,
    used_turnover: Decimal,
    max_turnover: Decimal,
) -> tuple[dict[AssetClass, Decimal], Decimal] | None:
    """Aksiyon B — Yüksek risk katkısını azalt: en yüksek RC%'li
    kategoriden, portföy volatilitesi profilin Hedef bandına inene kadar
    transfer eder."""
    rc = _risk_contributions(weights, category_vols, correlations, current_vol)
    if not rc:
        return None
    donor = max(rc, key=lambda ac: rc[ac])
    target_vol = _target_volatility(profile, current_vol)
    if current_vol <= target_vol:
        return None

    def should_stop(w: dict[AssetClass, Decimal]) -> bool:
        vol = _portfolio_volatility_from_categories(w, category_vols, correlations)
        return vol is None or vol <= target_vol

    return _run_transfer_loop(
        profile, weights, donor, correlations, should_stop, used_turnover, max_turnover
    )


def _apply_action_c(
    profile: RiskProfile,
    weights: dict[AssetClass, Decimal],
    category_vols: dict[AssetClass, float],
    correlations: dict[tuple[AssetClass, AssetClass], float],
    used_turnover: Decimal,
    max_turnover: Decimal,
) -> tuple[dict[AssetClass, Decimal], Decimal] | None:
    """Aksiyon C — Çeşitlendirmeyi güçlendir: en yüksek ikili korelasyonlu
    çiftin RC%'si daha yüksek olan tarafından, DR hedefe (RISK_SCENARIO_DR_
    TARGET) ulaşana kadar transfer eder. Alıcı, `_select_receiver`'ın
    "en düşük ortalama korelasyonlu" kuralıyla zaten doğal olarak seçilir."""
    pair = _highest_correlated_pair(weights, correlations)
    if pair is None:
        return None
    vol_now = _portfolio_volatility_from_categories(weights, category_vols, correlations)
    if vol_now is None or vol_now <= 0:
        return None
    rc = _risk_contributions(weights, category_vols, correlations, vol_now)
    a, b = pair
    donor = a if rc.get(a, 0.0) >= rc.get(b, 0.0) else b

    def should_stop(w: dict[AssetClass, Decimal]) -> bool:
        vol = _portfolio_volatility_from_categories(w, category_vols, correlations)
        if vol is None or vol <= 0:
            return True
        dr = _diversification_ratio(w, category_vols, vol)
        return dr is not None and dr >= settings.risk_scenario_dr_target

    if should_stop(weights):
        return None
    return _run_transfer_loop(
        profile, weights, donor, correlations, should_stop, used_turnover, max_turnover
    )


def _generate_combinations() -> list[list[str]]:
    """KK-1: aksiyonlar her zaman A→B→C sırasıyla uygulanır; kombinasyonlar
    bu sırayı korur ([A],[B],[C],[A,B],[A,C],[B,C],[A,B,C])."""
    combos: list[list[str]] = []
    for size in range(1, len(_ACTION_KEYS) + 1):
        combos.extend(list(c) for c in combinations(_ACTION_KEYS, size))
    return combos


def _run_scenario(
    profile: RiskProfile,
    action_keys: list[str],
    initial_weights: dict[AssetClass, Decimal],
    category_vols: dict[AssetClass, float],
    correlations: dict[tuple[AssetClass, AssetClass], float],
) -> dict:
    """Bir aksiyon kombinasyonunu sırasıyla uygular (KK-1). KK-2: kombinasyon
    içindeki tüm aksiyonlar TEK bir 30 puanlık turnover bütçesini paylaşır."""
    max_turnover = Decimal(str(settings.risk_scenario_max_turnover_percent)) / 100
    used_turnover = _ZERO
    current = dict(initial_weights)
    applied: list[str] = []
    vol_before = _portfolio_volatility_from_categories(current, category_vols, correlations)

    for key in action_keys:
        if used_turnover >= max_turnover:
            break
        vol_now = _portfolio_volatility_from_categories(current, category_vols, correlations)
        if vol_now is None:
            break

        if key == "A":
            result = _apply_action_a(
                profile, current, category_vols, correlations, used_turnover, max_turnover
            )
        elif key == "B":
            result = _apply_action_b(
                profile, current, category_vols, correlations, vol_now, used_turnover, max_turnover
            )
        else:
            result = _apply_action_c(
                profile, current, category_vols, correlations, used_turnover, max_turnover
            )

        if result is None:
            continue
        new_weights, new_used = result
        if new_used > used_turnover:
            current, used_turnover = new_weights, new_used
            applied.append(key)

    vol_after = _portfolio_volatility_from_categories(current, category_vols, correlations)
    return {
        "weights": current,
        "actions_applied": applied,
        "turnover": used_turnover,
        "volatility_before": vol_before,
        "volatility_after": vol_after,
    }


def _evaluate_scenario(initial_vol: float, result: dict, target_vol: float) -> tuple[bool, float]:
    """Eleme: turnover eşik altındaysa VEYA (hedef bandın içine girmemişse
    VE göreli risk azalması eşik altındaysa) senaryo elenir."""
    turnover_percent = float(result["turnover"] * 100)
    if turnover_percent < settings.risk_scenario_min_turnover_percent:
        return False, 0.0

    vol_after = result["volatility_after"]
    if vol_after is None or initial_vol is None or initial_vol <= 0:
        return False, 0.0

    within_band = vol_after <= target_vol
    relative_reduction = (initial_vol - vol_after) / initial_vol
    if not within_band and relative_reduction < settings.risk_scenario_min_relative_risk_reduction:
        return False, 0.0

    risk_reduction_ratio = max(0.0, relative_reduction)
    turnover_component = 1.0 - min(
        1.0, turnover_percent / settings.risk_scenario_max_turnover_percent
    )
    score = (
        settings.risk_scenario_score_risk_weight * risk_reduction_ratio
        + settings.risk_scenario_score_turnover_weight * turnover_component
    )
    return True, score


def _scenario_label(turnover_percent: float) -> str:
    if turnover_percent <= settings.risk_scenario_label_small_max_turnover:
        return "Küçük Düzeltme"
    if turnover_percent <= settings.risk_scenario_label_balanced_max_turnover:
        return "Dengeli Düzeltme"
    return "Belirgin Düzeltme"


def _dedup_scenarios(scenarios: list[dict]) -> list[dict]:
    """±1 puan turnover içindeki senaryoları tekilleştirir, yüksek skorlu
    olanı tutar."""
    ordered = sorted(scenarios, key=lambda s: s["score"], reverse=True)
    kept: list[dict] = []
    for candidate in ordered:
        if any(abs(candidate["turnover_percent"] - k["turnover_percent"]) <= 1.0 for k in kept):
            continue
        kept.append(candidate)
    return kept


def _asset_breakdown(
    profile: RiskProfile,
    category_before: dict[AssetClass, Decimal],
    category_after: dict[AssetClass, Decimal],
    asset_ids_by_class: dict[AssetClass, list[UUID]],
    market_values: dict[UUID, Decimal],
    symbol_by_asset_id: dict[UUID, str],
    total_value: Decimal,
) -> list[ScenarioAssetWeight]:
    """Kategori ağırlığı değiştiğinde, kategorideki her varlık kendi payı
    oranında ölçeklenir (belge §6.5). Varlık bazlı üst sınır
    (RISK_MAX_ASSET_WEIGHT) burada uygulanır; kırpılan fazla diğer varlıklara
    yeniden dağıtılmaz — belge bu durumu tanımlamıyor, basit bir tasarım
    tercihi."""
    max_asset_weight = RISK_MAX_ASSET_WEIGHT[profile]
    result: list[ScenarioAssetWeight] = []
    for asset_class, asset_ids in asset_ids_by_class.items():
        before_cat = category_before.get(asset_class, _ZERO)
        after_cat = category_after.get(asset_class, _ZERO)
        scale = (after_cat / before_cat) if before_cat > 0 else _ZERO
        for asset_id in asset_ids:
            current_value = market_values[asset_id]
            current_percent = current_value / total_value if total_value > 0 else _ZERO
            proposed_percent = min(current_percent * scale, max_asset_weight)
            proposed_value = proposed_percent * total_value
            result.append(
                ScenarioAssetWeight(
                    asset_symbol=symbol_by_asset_id[asset_id],
                    asset_class=asset_class,
                    current_percent=_round2(current_percent * 100),
                    proposed_percent=_round2(proposed_percent * 100),
                    current_value=_round2(current_value),
                    proposed_value=_round2(proposed_value),
                )
            )
    return result


def _generate_rebalance_scenarios(
    profile: RiskProfile,
    category_weights: dict[AssetClass, Decimal],
    category_vols: dict[AssetClass, float],
    correlations: dict[tuple[AssetClass, AssetClass], float],
    current_vol: float,
    asset_ids_by_class: dict[AssetClass, list[UUID]],
    market_values: dict[UUID, Decimal],
    symbol_by_asset_id: dict[UUID, str],
    total_value: Decimal,
) -> list[RebalanceScenario]:
    """7 kombinasyonu (A,B,C,AB,AC,BC,ABC) dener, eler, tekilleştirir ve en
    iyi RISK_SCENARIO_TOP_N tanesini döner (yüksek skor önce)."""
    target_vol = _target_volatility(profile, current_vol)
    evaluated: list[dict] = []

    for action_keys in _generate_combinations():
        result = _run_scenario(profile, action_keys, category_weights, category_vols, correlations)
        if not result["actions_applied"]:
            continue
        is_valid, score = _evaluate_scenario(current_vol, result, target_vol)
        if not is_valid:
            continue
        evaluated.append(
            {
                "actions_applied": result["actions_applied"],
                "weights_before": category_weights,
                "weights_after": result["weights"],
                "volatility_before": result["volatility_before"],
                "volatility_after": result["volatility_after"],
                "turnover_percent": float(result["turnover"] * 100),
                "score": score,
            }
        )

    top = _dedup_scenarios(evaluated)[: settings.risk_scenario_top_n]

    scenarios: list[RebalanceScenario] = []
    for item in top:
        asset_weights = _asset_breakdown(
            profile,
            item["weights_before"],
            item["weights_after"],
            asset_ids_by_class,
            market_values,
            symbol_by_asset_id,
            total_value,
        )
        category_weight_schemas = [
            ScenarioCategoryWeight(
                asset_class=ac,
                current_percent=_round2(item["weights_before"].get(ac, _ZERO) * 100),
                proposed_percent=_round2(item["weights_after"].get(ac, _ZERO) * 100),
            )
            for ac in AssetClass
        ]
        scenarios.append(
            RebalanceScenario(
                actions_applied=item["actions_applied"],
                label=_scenario_label(item["turnover_percent"]),
                category_weights=category_weight_schemas,
                asset_weights=asset_weights,
                volatility_before_percent=_round2(Decimal(str(item["volatility_before"] * 100))),
                volatility_after_percent=_round2(Decimal(str(item["volatility_after"] * 100))),
                risk_level_before=_risk_level_from_volatility(item["volatility_before"]),
                risk_level_after=_risk_level_from_volatility(item["volatility_after"]),
                turnover_percent=_round2(Decimal(str(item["turnover_percent"]))),
                score=_round4(Decimal(str(item["score"]))),
            )
        )
    return scenarios


# --------------------------------------------------------------------------
# Ana giriş noktası
# --------------------------------------------------------------------------


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
        risk_level=None,
        is_within_profile=None,
        metrics=RiskMetrics(
            annualized_volatility_percent=None,
            max_drawdown_percent=None,
            category_metrics=[],
            category_correlation_matrix=[],
            diversification_ratio=None,
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
            holdings_count=0,
            asset_class_count=0,
            price_points_used=0,
        ),
        causes=None,
        scenarios=[],
        warnings=[_EMPTY_PORTFOLIO_WARNING],
    )


def get_risk_assessment(
    db: Session,
    user_id: UUID,
    profile_override: RiskProfile | None = None,
    include_scenarios: bool = False,
) -> RiskAssessment:
    """Kullanıcının portföy riskini v2 metodolojisiyle değerlendirir.

    `profile_override` verilirse hesaplama o profile göre yapılır ama
    kullanıcının DB'deki kalıcı profili değişmez — "ya agresif olsaydım?"
    senaryosu için.

    `include_scenarios`: ÜRÜN SAHİBİ KARARIYLA (2026-08) devre dışı — bu
    parametre True verilse bile `settings.risk_scenarios_enabled=False`
    olduğu sürece `scenarios` her zaman boş liste döner. Risk artık yalnızca
    tespit/uyarı içindir ("profilinize göre riskiniz yüksek"); ne yapılması
    gerektiğini önermek kapsam dışı bırakıldı — kullanıcının kendi yatırım
    kararı. Motor kod olarak duruyor, ileride ürün kararı değişirse
    `risk_scenarios_enabled=True` yapmak yeterli."""
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
    asset_ids_by_class: dict[AssetClass, list[UUID]] = {}
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
        asset_class = holding.asset.asset_class
        class_values[asset_class] = class_values.get(asset_class, _ZERO) + value
        asset_ids_by_class.setdefault(asset_class, []).append(holding.asset_id)

    # Serbest nakit (defterden): toplam değere ve CASH dilimine eklenir —
    # portfolio_service ile aynı ilke.
    asset_only_total = sum(market_values.values(), start=_ZERO)
    cash_balance = cash_balance_as_of(db, portfolio.id)
    total_value = asset_only_total + cash_balance
    if cash_balance != 0:
        class_values[AssetClass.CASH] = class_values.get(AssetClass.CASH, _ZERO) + cash_balance

    if total_value <= 0:
        return _empty_assessment(user_id, profile, source, risk_free_rate, rf_is_live)

    # v2: ağırlıklar TOPLAM portföy üzerinden (nakit dahil) — nakit de bir
    # kategoridir (RISK_MAX_CATEGORY_WEIGHT[CASH], RISK_DEFENSE_FLOOR), v1'in
    # aksine hesap dışı bırakılmıyor.
    weights = {aid: value / total_value for aid, value in market_values.items()}
    category_weights = {ac: class_values.get(ac, _ZERO) / total_value for ac in AssetClass}

    top_asset_id = max(weights, key=lambda aid: weights[aid])
    max_asset_weight = weights[top_asset_id]
    top_class = max(class_values, key=lambda ac: class_values[ac])
    max_class_weight = class_values[top_class] / total_value

    # HHI: yalnızca yatırılan varlıklar üzerinden (nakit hariç) — sabit,
    # risksiz bir pozisyonun "çeşitlendirme sorunu" gibi görünmesi yanıltıcı
    # olur; nakidin kendi yoğunlaşması zaten max_category_weight ile yakalanır.
    hhi_weights = (
        {aid: value / asset_only_total for aid, value in market_values.items()}
        if asset_only_total > 0
        else {}
    )
    herfindahl = sum((w * w for w in hhi_weights.values()), start=_ZERO)

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
    volatility = drawdown = portfolio_return = sharpe = None
    var_try = var_percent = diversification_ratio_value = None
    category_metrics: list[CategoryMetrics] = []
    correlation_pairs: list[CategoryCorrelationPair] = []
    causes: RiskCauseDiagnosis | None = None
    scenarios: list[RebalanceScenario] = []
    risk_level: RiskLevel | None = None
    is_within_profile: bool | None = None

    if price_points >= settings.risk_min_price_points:
        value_series = [
            sum((h.quantity * try_series[h.asset_id][day] for h in holdings), start=_ZERO)
            for day in sorted_dates
        ]
        portfolio_value_returns = _daily_returns(value_series)
        drawdown = _max_drawdown(value_series)
        portfolio_return = _annualized_mean_return(portfolio_value_returns)

        category_returns = _category_returns(
            class_values, asset_ids_by_class, try_series, market_values, sorted_dates
        )
        category_vols = {
            ac: _annualized_volatility(returns) for ac, returns in category_returns.items()
        }
        correlations = _category_correlation_matrix(category_returns)

        volatility = _portfolio_volatility_from_categories(
            category_weights, category_vols, correlations
        )

        if volatility is not None:
            risk_level = _risk_level_from_volatility(volatility)
            band_upper = float(RISK_TARGET_VOLATILITY_BAND[profile][1])
            is_within_profile = volatility <= band_upper

            diversification_ratio_value = _diversification_ratio(
                category_weights, category_vols, volatility
            )
            risk_contributions = _risk_contributions(
                category_weights, category_vols, correlations, volatility
            )

            for ac in AssetClass:
                cat_vol = category_vols.get(ac)
                category_metrics.append(
                    CategoryMetrics(
                        asset_class=ac,
                        weight_percent=_round2(category_weights.get(ac, _ZERO) * 100),
                        annualized_volatility_percent=(
                            _round2(Decimal(str(cat_vol * 100))) if cat_vol is not None else None
                        ),
                        risk_contribution_percent=(
                            _round2(Decimal(str(risk_contributions[ac] * 100)))
                            if ac in risk_contributions
                            else None
                        ),
                    )
                )
            for (a, b), corr in correlations.items():
                correlation_pairs.append(
                    CategoryCorrelationPair(
                        category_a=a, category_b=b, correlation=_round4(Decimal(str(corr)))
                    )
                )

            if not is_within_profile:
                asset_vols = {
                    aid: _annualized_volatility(
                        _returns_aligned([try_series[aid][day] for day in sorted_dates])
                    )
                    for aid in asset_ids
                }
                causes = _diagnose_causes(
                    max_asset_weight=max_asset_weight,
                    max_asset_symbol=symbol_by_asset_id[top_asset_id],
                    category_weights=category_weights,
                    herfindahl=herfindahl,
                    asset_vols=asset_vols,
                    asset_weights=weights,
                    risk_contributions=risk_contributions,
                    correlations=correlations,
                    diversification_ratio=diversification_ratio_value,
                )
                # ÜRÜN SAHİBİ KARARI (2026-08): senaryo önerisi ürün
                # kapsamından çıkarıldı (bkz. Settings.risk_scenarios_enabled
                # yanındaki not). Motor kod olarak duruyor ama bu bayrak
                # False olduğu sürece hiçbir zaman tetiklenmez — çağıran
                # include_scenarios=True verse bile.
                if include_scenarios and settings.risk_scenarios_enabled:
                    scenarios = _generate_rebalance_scenarios(
                        profile,
                        category_weights,
                        category_vols,
                        correlations,
                        volatility,
                        asset_ids_by_class,
                        market_values,
                        symbol_by_asset_id,
                        total_value,
                    )
        else:
            warnings.append(_missing_category_data_warning())

        # VaR (parametrik, AK 2.4).
        if volatility is not None:
            z = _inverse_normal_cdf(settings.risk_var_confidence)
            daily_vol = volatility / math.sqrt(settings.risk_trading_days_per_year)
            horizon_vol = daily_vol * math.sqrt(settings.risk_var_horizon_days)
            var_ratio = z * horizon_vol
            var_percent = Decimal(str(var_ratio * 100))
            var_try = Decimal(str(var_ratio)) * total_value

        # Sharpe oranı (AK 2.5).
        if portfolio_return is not None and volatility not in (None, 0):
            sharpe = (portfolio_return - risk_free_rate) / volatility
    else:
        warnings.append(_insufficient_history_warning(price_points))

    return RiskAssessment(
        user_id=user_id,
        as_of=max(as_of_dates) if as_of_dates else date.today(),
        risk_profile=profile,
        risk_profile_source=source,
        total_value=_round2(total_value),
        risk_level=risk_level,
        is_within_profile=is_within_profile,
        metrics=RiskMetrics(
            annualized_volatility_percent=(
                _round2(Decimal(str(volatility * 100))) if volatility is not None else None
            ),
            max_drawdown_percent=(
                _round2(Decimal(str(drawdown * 100))) if drawdown is not None else None
            ),
            category_metrics=category_metrics,
            category_correlation_matrix=correlation_pairs,
            diversification_ratio=(
                _round2(Decimal(str(diversification_ratio_value)))
                if diversification_ratio_value is not None
                else None
            ),
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
            holdings_count=len(holdings),
            asset_class_count=len(class_values),
            price_points_used=price_points,
        ),
        causes=causes,
        scenarios=scenarios,
        warnings=warnings,
    )
