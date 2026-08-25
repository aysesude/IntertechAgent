"""Kullanıcı risk profili uçlarının şemaları.

ÜRÜN SAHİBİ NOTU (Not 1 ve Not 4, 2026-08): "risk kişinin yatırım eylemidir;
yapılan test sonucu kullanıcı sisteme bildirir." Profil sistem tarafından
portföyden TÜRETİLMEZ — kullanıcı anketi doldurur, sonucu buraya bildirir,
portföy ondan sonra ona göre kurulur. Bu dosya o bildirimin sözleşmesidir.

KADEME SAYISI BİLİNÇLİ OLARAK SABİTLENMEDİ. Alanların tipi `RiskProfile`
enum'ının kendisidir, string ya da sayı değil. Profil kademesi ileride
4'ten 7'ye çıkarılırsa (karar bekliyor) bu dosyada, serviste ve uçta
DEĞİŞİKLİK GEREKMEZ: doğrulama, OpenAPI şeması ve `available_profiles`
listesi enum'dan türediği için kendiliğinden genişler. Değişmesi gereken
yerler yalnızca enum'ın kendisi, veritabanı enum'ı (migration) ve
config.py'deki profil bazlı tablolardır.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import RiskProfile


class RiskProfileUpdate(BaseModel):
    """Anket sonucunun sisteme bildirilmesi (istek gövdesi).

    Tanınmayan bir değer Pydantic tarafından 422 ile reddedilir; uçta ayrıca
    elle doğrulama yazılmadı — iki farklı hata mesajı üretmemek için."""

    model_config = ConfigDict(frozen=True)

    risk_profile: RiskProfile = Field(
        description="Anket sonucunda belirlenen risk profili",
    )


class UserRiskProfile(BaseModel):
    """Kullanıcının kayıtlı risk profili (yanıt gövdesi).

    `available_profiles` kasıtlı olarak burada dönüyor: anket ekranının
    seçenekleri kendi tarafında sabit yazmasını engeller. Kademe sayısı
    değiştiğinde arayüz kod değişikliği olmadan yeni seçenekleri görür."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    risk_profile: RiskProfile
    available_profiles: list[RiskProfile]
