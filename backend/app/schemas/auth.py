"""Giriş uçlarının ekip sözleşmesi (FR-0).

Alan adları İngilizce (CLAUDE.md: kod İngilizce, kullanıcıya görünen metin
Türkçe). Arayüzdeki "T.C. Kimlik Numarası" alanı `national_id`'ye eşlenir.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import RiskProfile


class LoginRequest(BaseModel):
    """Giriş isteği.

    Uzunluk kısıtları burada da var, arayüzde de: arayüz doğrulaması kullanıcı
    konforu içindir ve atlatılabilir; sunucu tarafındaki asıl kapıdır. Ama
    T.C. kimlik numarasının SAĞLAMA (checksum) doğrulaması bilerek YAPILMIYOR
    — geçersiz bir numara zaten hiçbir satırla eşleşmez ve ayrı bir hata
    mesajı üretmek "bu numara sistemde kayıtlı mı" sorusuna dolaylı cevap
    verirdi.
    """

    model_config = ConfigDict(frozen=True)

    national_id: str = Field(min_length=11, max_length=11, description="T.C. kimlik numarası")
    password: str = Field(min_length=1, max_length=128)


class AuthUser(BaseModel):
    """Giriş yapmış kullanıcının arayüze dönen bilgisi.

    E-posta DAHİL DEĞİL, T.C. kimlik numarası DAHİL DEĞİL: arayüzün ikisine de
    ihtiyacı yok (başlıkta ad ve baş harfler gösteriliyor), token'ın taşıdığı
    kişisel veriyi en aza indiriyoruz.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    full_name: str
    risk_profile: RiskProfile


class TokenResponse(BaseModel):
    """Başarılı giriş yanıtı.

    `expires_in` saniye cinsindendir ve sunucudan gelir; istemci kendi süre
    hesabını yapmasın diye. `user` aynı yanıtta dönüyor ki arayüz giriş
    sonrası ikinci bir istek atmak zorunda kalmasın.
    """

    model_config = ConfigDict(frozen=True)

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUser


class PasswordResetRequest(BaseModel):
    """Yenileme başlatma isteği.

    Yanıt, kimliğin KAYITLI OLUP OLMADIĞINI bildirmez: aksi halde bu uç
    "hangi T.C. kimlik numaraları sistemde var" sorusunu tek tek denemeye
    açık bir araca dönüşürdü (giriş ucundaki aynı gerekçe).
    """

    model_config = ConfigDict(frozen=True)

    national_id: str = Field(min_length=11, max_length=11, description="T.C. kimlik numarası")


class PasswordResetInfo(BaseModel):
    """Yenileme başlatıldı bilgisi.

    Kodun kendisi DÖNMEZ. Kaç haneli olduğu ve ne kadar geçerli olduğu
    arayüzün alanı ve geri sayımı kurabilmesi için dönüyor — ikisini de
    arayüzde sabit yazmamak için.
    """

    model_config = ConfigDict(frozen=True)

    code_length: int
    expires_in_seconds: int


class PasswordResetComplete(BaseModel):
    """Yenilemeyi tamamlama isteği."""

    model_config = ConfigDict(frozen=True)

    national_id: str = Field(min_length=11, max_length=11)
    code: str = Field(min_length=1, max_length=32)
    # Giriş ekranı 6 haneli sayısal şifre bekliyor; yenileme de aynı biçimi
    # üretmek zorunda, yoksa kullanıcı giriş yapamayacağı bir şifre belirler.
    new_password: str = Field(min_length=6, max_length=6)

    @field_validator("new_password")
    @classmethod
    def _yalnizca_rakam(cls, deger: str) -> str:
        if not deger.isdigit():
            raise ValueError("Şifre yalnızca rakamlardan oluşmalı.")
        return deger
