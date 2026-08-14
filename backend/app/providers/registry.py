"""Varlık başına sağlayıcı zinciri: hangi varlığın serisi/spotu hangi sıerayla
hangi kaynaklardan denenir.

Zarif düşüş kalıbı (NFR): zincirdeki kaynaklar sırayla denenir; hepsi
başarısızsa ingest servisi durumu `data_ingest_log`'a yazar ve DB'deki son
bilinen fiyatlar yerinde kalır (silme yok). Yani "canlı -> DB'deki son kayıt"
düşüşü kendiliğinden gerçekleşir; sabit varsayılan fiyat yalnızca sentetik
seed'de vardır.

Sağlayıcılar saftır (DB importu yasak) — bu modül de öyledir. DB'ye yazan
tek yer `services/price_ingest.py`'dir.
"""

from app.core.config import PriceSource, settings
from app.providers.base import PriceProvider
from app.providers.isportfoy import IsPortfoyProvider
from app.providers.tcmb import TcmbEvdsProvider, TcmbTodayProvider
from app.providers.tefas_p import TefasProvider
from app.providers.universe import AssetSpec
from app.providers.yfinance_p import YFinanceGramMetalProvider, YFinanceProvider

# (sağlayıcı, o sağlayıcının anladığı sembol) ikilisi
ProviderStep = tuple[PriceProvider, str]


def series_chain(spec: AssetSpec) -> list[ProviderStep]:
    """Tarihsel seri için deneme zinciri. Boş liste = canlı kaynak yok
    (sentetik/türetilmiş varlık; ingest bunları ayrıca ele alır)."""
    if spec.data_source == PriceSource.TCMB_EVDS:
        chain: list[ProviderStep] = []
        if settings.evds_api_key:
            chain.append((TcmbEvdsProvider(settings.evds_api_key), spec.provider_symbol))
        if spec.yf_symbol:
            chain.append((YFinanceProvider(), spec.yf_symbol))
        return chain
    if spec.data_source == PriceSource.YFINANCE:
        provider = YFinanceGramMetalProvider() if spec.ons_to_gram else YFinanceProvider()
        return [(provider, spec.provider_symbol)]
    if spec.data_source == PriceSource.TEFAS:
        return [(TefasProvider(), spec.provider_symbol)]
    # SYNTHETIC ve DERIVED: canlı seri kaynağı yok.
    return []


def latest_chain(spec: AssetSpec) -> list[ProviderStep]:
    """Spot (bugünün) fiyatı için deneme zinciri. Spot uçlar öne gelir:
    döviz için TCMB today.xml (resmî), fon için İş Portföy yedeği."""
    if spec.data_source == PriceSource.TCMB_EVDS:
        chain = [(TcmbTodayProvider(), spec.tcmb_code)]
        if spec.yf_symbol:
            chain.append((YFinanceProvider(), spec.yf_symbol))
        return chain
    if spec.data_source == PriceSource.TEFAS:
        return [
            (TefasProvider(), spec.provider_symbol),
            (IsPortfoyProvider(), spec.provider_symbol),
        ]
    return series_chain(spec)
