"""Sinyal tabanlı, LLM yorumlu portföy risk değerlendirmesi ("riskk" bölümü,
Google Drive "Intertech - Ekip 3" dokümanı, iş analisti güncellemesi 2026-08).

BU MODÜL `app/schemas/risk.py`'DEKİ `RiskAssessment`'TAN TAMAMEN BAĞIMSIZDIR.
`RiskAssessment` volatilite/VaR/Sharpe/korelasyon temelli, sayısal ve
`risk_service.py` tarafından HESAPLANAN bir çıktıdır (FR-4). İş Analisti'nin
2026-08-22 açıklamasıyla bu iki yapı AYRI, birbirinin yerine geçmeyen iki
metrik seti olarak duruyor — biri birleştirilip diğeri kaldırılmıyor.

Buradaki `RiskSignalAssessment` ise TAMAMEN LLM tarafından üretilir: hiçbir
alan kod tarafında hesaplanmaz/sınıflandırılmaz (bkz. agents/risk_agent.py,
agents/prompts/risk_signals.md — "Risk, geçmiş fiyat oynaklığından değil
şuanki durumdan çıkar", iş analisti notu). Bu şema yalnızca LLM çıktısının
BEKLENEN ŞEKLE uyduğunu doğrulamak için var; sayısal/mantıksal bir doğruluk
garantisi DEĞİL, yapısal bir doğrulamadır.

Bilinen, çözülmemiş sınır: iş analistinin kabul kriteri "aynı portföy için
tekrarlanan çalıştırmalarda risk seviyesi en fazla bir kademe oynar" der. Bu
kod tarafında GARANTİ EDİLEMEZ — LLM çıktısı deterministik değildir. Şema ve
agent bunu zorlayamaz; yalnızca prompt'ta istenir (bkz. risk_signals.md).
Benzer şekilde "emir kipi yok" ve "her bulgu kaynaklı" kuralları da yalnızca
prompt seviyesinde istenir, kod bunu doğrulamaz.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RiskSignalLevel(str, Enum):
    """5 kademeli, sinyal tabanlı risk seviyesi — `app.core.config.RiskLevel`
    (7 kademeli, volatilite tabanlı) ile KARIŞTIRILMAMALI; ayrı bir eksen."""

    AZ_RISKLI = "az_riskli"
    AZ_ORTA_RISKLI = "az_orta_riskli"
    ORTA_RISKLI = "orta_riskli"
    ORTA_YUKSEK_RISKLI = "orta_yuksek_riskli"
    COK_YUKSEK_RISKLI = "cok_yuksek_riskli"


class RiskSignalCode(str, Enum):
    """Dokümandaki 5 sinyal — LLM yalnızca bunlardan birini kullanabilir,
    başka bir sinyal kodu uyduramaz (Pydantic doğrular)."""

    KONSANTRASYON = "konsantrasyon"
    SEKTOR_YOGUNLASMASI = "sektor_yogunlasmasi"
    OLUMSUZ_HABER = "olumsuz_haber"
    SEKTOR_GELISMESI = "sektor_gelismesi"
    PROFIL_SAPMASI = "profil_sapmasi"


class RiskSignalFinding(BaseModel):
    """Portföydeki bir varlık için tek bir sinyal bulgusu."""

    model_config = ConfigDict(frozen=True)

    asset_symbol: str
    weight_percent: float
    signal: RiskSignalCode
    explanation: str
    # olumsuz_haber/sektor_gelismesi icin EN AZ bir kaynak beklenir (prompt
    # kurali); konsantrasyon/sektor_yogunlasmasi/profil_sapmasi icin bos
    # kalabilir — kod bunu ZORUNLU KILMAZ, yalnizca prompt ister.
    sources: list[str] = Field(default_factory=list)


class RiskSignalAssessment(BaseModel):
    """LLM'in `agents/prompts/risk_signals.md`'ye göre ürettiği yapısal çıktı.

    `confidence`, kaynak dokümanların yeterliliğine göre LLM'in kendi beyanı;
    `covered_weight_percent` gibi kod-hesaplı bir eşikle ÇAPRAZLANMAZ (bu
    bilinçli bir sınırlamadır, ölçülebilir bir doğrulama değildir)."""

    model_config = ConfigDict(frozen=True)

    risk_level: RiskSignalLevel
    general_assessment: str
    profile_fit: str
    risky_assets: list[RiskSignalFinding]
    rebalancing: str
    investment_strategy: str
    confidence: Literal["normal", "dusuk"]
    # Anket henüz yok (bkz. risk_agent.py _DUMMY_SURVEY_SCORE_BY_PROFILE):
    # bu alan True iken kullanıcıya "anket sonucunuz" diye sunulmamalı.
    survey_score_is_dummy: bool
