"""Anket risk puanı (1-7): eşleme, servis, uç.

Şartname: "Kullanıcıların çözdüğü anket sonucu 1-7 arası bir risk puanı olur."
Bugüne kadar o puanın yaşayacağı bir yer yoktu; `users.risk_profile` dört
kademeliydi ve uygunluk kontrolü yedi kademelik bir puan bekliyordu. Aradaki
boşluk `agents/risk_agent.py` içinde GEÇİCİ bir profil→puan eşlemesiyle
dolduruluyordu.

İki ölçek artık yan yana yaşıyor: **puan yetkili, profil türev.** Bu dosya
o ilişkinin bozulmadığını kilitliyor.
"""

import pytest
from sqlalchemy import select

from app.core.config import (
    RISK_SURVEY_SCORE_MAX,
    RISK_SURVEY_SCORE_MIN,
    RiskProfile,
    risk_profile_for_survey_score,
    survey_score_band,
)
from app.models import User
from app.services.user_service import (
    get_user_risk_survey,
    set_user_risk_profile,
    set_user_risk_survey,
)


class TestEsleme:
    """Puan → profil eşlemesi. `config.py` açılışta zaten doğruluyor; burada
    ikinci kez kontrol edilmesinin sebebi o doğrulamanın yanlışlıkla
    kaldırılması durumunda testin sessiz kalmaması."""

    def test_yedi_puanin_hepsi_bir_profile_esleniyor(self):
        for puan in range(RISK_SURVEY_SCORE_MIN, RISK_SURVEY_SCORE_MAX + 1):
            assert isinstance(risk_profile_for_survey_score(puan), RiskProfile)

    def test_dort_profilin_hepsi_kullaniliyor(self):
        """Kullanılmayan bir profil, risk motorunun o profil için taşıdığı
        tüm tabloların (hedef dağılım, volatilite bandı, savunma tabanı) ölü
        koda dönmesi demek olurdu."""
        uretilen = {risk_profile_for_survey_score(p) for p in range(1, 8)}
        assert uretilen == set(RiskProfile)

    def test_puan_arttikca_profil_geri_gitmez(self):
        """ "Puanım arttı ama profilim muhafazakâra düştü" mümkün olmamalı."""
        sira = [
            RiskProfile.CONSERVATIVE,
            RiskProfile.BALANCED,
            RiskProfile.GROWTH,
            RiskProfile.AGGRESSIVE,
        ]
        indeksler = [sira.index(risk_profile_for_survey_score(p)) for p in range(1, 8)]
        assert indeksler == sorted(indeksler)

    def test_bantlar_varlik_merdiveniyle_hizali(self):
        """Bantlar keyfi değil: her profil, kendi bandının açtığı varlık
        kümesiyle örtüşüyor (1-2 nakit/tahvil, 3-4 +döviz/maden, 5 +yerli
        hisse, 6-7 +yabancı hisse/serbest fon)."""
        assert survey_score_band(RiskProfile.CONSERVATIVE) == (1, 2)
        assert survey_score_band(RiskProfile.BALANCED) == (3, 4)
        assert survey_score_band(RiskProfile.GROWTH) == (5, 5)
        assert survey_score_band(RiskProfile.AGGRESSIVE) == (6, 7)


def _kullanici(db_session, **alanlar) -> User:
    user = User(
        email=alanlar.pop("email", "anket@test.local"),
        full_name="Anket Test",
        risk_profile=alanlar.pop("risk_profile", RiskProfile.BALANCED),
        **alanlar,
    )
    db_session.add(user)
    db_session.commit()
    return user


class TestServis:
    def test_puan_yazilinca_profil_de_turetiliyor(self, db_session):
        """İkisi TEK işlemde yazılmalı. Ayrı yazılsalardı arada bir hata
        olduğunda kullanıcı puanı 6 ama profili Muhafazakâr olan bir satırla
        kalır ve risk motoru yanlış tabloyu kullanırdı."""
        user = _kullanici(db_session, risk_profile=RiskProfile.CONSERVATIVE)

        sonuc = set_user_risk_survey(db_session, user.id, 6)

        assert sonuc.risk_survey_score == 6
        assert sonuc.risk_profile is RiskProfile.AGGRESSIVE
        assert sonuc.score_band == (6, 7)

        taze = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
        assert taze.risk_survey_score == 6
        assert taze.risk_profile is RiskProfile.AGGRESSIVE

    def test_puan_yazilinca_guncelleme_zamani_damgalaniyor(self, db_session):
        """Sinyal 5 Yol A'nın (profil_sapmasi) tetikleyicisi budur — bkz.
        docs/notes/sinyal5-olay-tabanli-aktivasyon-tasarimi.md §4.3.
        `risk_survey_updated_at` puan/profille AYNI transaction'da yazılmalı,
        aksi hâlde "olay" bir sonraki değerlendirmeye kadar görünmez kalır."""
        user = _kullanici(db_session)
        assert user.risk_survey_updated_at is None

        set_user_risk_survey(db_session, user.id, 6)

        taze = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
        assert taze.risk_survey_updated_at is not None
        # Tüketim henüz hiç olmadı: "bekleyen olay var" tanımı burada sağlanmalı.
        assert taze.risk_survey_event_consumed_at is None

    def test_puan_yoksa_bant_da_yok(self, db_session):
        """Anketi doldurmamış kullanıcıya kayıtlı profilin bandını döndürmek,
        vermediği bir cevabı vermiş gibi göstermek olurdu (AK 5.5)."""
        user = _kullanici(db_session, risk_profile=RiskProfile.GROWTH)

        sonuc = get_user_risk_survey(db_session, user.id)

        assert sonuc.risk_survey_score is None
        assert sonuc.score_band is None
        # Profil yine de dolu: `users.risk_profile` her satırda zorunlu.
        assert sonuc.risk_profile is RiskProfile.GROWTH

    def test_profil_dogrudan_yazilinca_puan_siliniyor(self, db_session):
        """Profil artık türev bir alan; doğrudan yazılması elle geçersiz
        kılmadır ve elde duran puan o değişikliği açıklamaz.

        Puan olduğu gibi bırakılsaydı birbirini tutmayan iki cevap saklanırdı:
        puan 6 (Agresif) derken profil Muhafazakâr görünürdü.
        """
        user = _kullanici(db_session)
        set_user_risk_survey(db_session, user.id, 6)

        set_user_risk_profile(db_session, user.id, RiskProfile.CONSERVATIVE)

        sonuc = get_user_risk_survey(db_session, user.id)
        assert sonuc.risk_survey_score is None
        assert sonuc.risk_profile is RiskProfile.CONSERVATIVE

    def test_profil_dogrudan_yazma_guncelleme_zamanina_dokunmuyor(self, db_session):
        """`set_user_risk_profile` (elle profil değiştirme) bir anket olayı
        DEĞİLDİR — bkz. tasarım belgesi §4.3 "değişmez" kararı. Elle yapılan
        bir değişikliğin Sinyal 5'i sahte biçimde tetiklemesi istenmiyor."""
        user = _kullanici(db_session)
        set_user_risk_survey(db_session, user.id, 6)
        ilk_damga = db_session.execute(
            select(User.risk_survey_updated_at).where(User.id == user.id)
        ).scalar_one()

        set_user_risk_profile(db_session, user.id, RiskProfile.CONSERVATIVE)

        son_damga = db_session.execute(
            select(User.risk_survey_updated_at).where(User.id == user.id)
        ).scalar_one()
        assert son_damga == ilk_damga

    def test_ayni_puan_tekrar_gonderilebilir(self, db_session):
        """İdempotent: anket ekranı aynı sonucu tekrar gönderebilir."""
        user = _kullanici(db_session)
        ilk = set_user_risk_survey(db_session, user.id, 4)
        ikinci = set_user_risk_survey(db_session, user.id, 4)
        assert ilk == ikinci

    @pytest.mark.parametrize("gecersiz", [0, -1, 8, 100])
    def test_aralik_disi_puan_serviste_de_reddediliyor(self, db_session, gecersiz):
        """Doğrulama Pydantic'te var ama servis HTTP katmanına güvenmemeli —
        seed ve betikler bu fonksiyonu doğrudan çağırıyor."""
        user = _kullanici(db_session)
        with pytest.raises(ValueError):
            set_user_risk_survey(db_session, user.id, gecersiz)


class TestUc:
    def test_ak_5_4_baskasinin_anket_puani_okunamaz(self, client_for, db_session):
        """Bir kullanıcının BAŞKASININ puanını görebilmesi, tüm uygunluk
        kontrolünün dayandığı beyanı sızdırmak olurdu."""
        sahip = _kullanici(db_session, email="sahip-anket@test.local")
        baskasi = _kullanici(db_session, email="baskasi-anket@test.local")

        yanit = client_for(sahip).get(f"/api/users/{baskasi.id}/risk-survey")
        assert yanit.status_code == 403

    def test_ak_5_4_baskasinin_anket_puani_yazilamaz(self, client_for, db_session):
        sahip = _kullanici(db_session, email="sahip-yaz@test.local")
        baskasi = _kullanici(db_session, email="baskasi-yaz@test.local")

        yanit = client_for(sahip).put(
            f"/api/users/{baskasi.id}/risk-survey",
            json={"risk_survey_score": 7},
        )
        assert yanit.status_code == 403

    @pytest.mark.parametrize("gecersiz", [0, 8, -3])
    def test_aralik_disi_puan_422(self, client_for, db_session, gecersiz):
        user = _kullanici(db_session, email=f"aralik{gecersiz}@test.local")
        yanit = client_for(user).put(
            f"/api/users/{user.id}/risk-survey",
            json={"risk_survey_score": gecersiz},
        )
        assert yanit.status_code == 422

    def test_olcek_sinirlari_yanitin_icinde(self, client_for, db_session):
        """Arayüz anket ölçeğini kendi tarafında sabit yazmasın diye."""
        user = _kullanici(db_session, email="olcek@test.local")
        yanit = client_for(user).get(f"/api/users/{user.id}/risk-survey")
        assert yanit.status_code == 200
        govde = yanit.json()
        assert govde["score_min"] == RISK_SURVEY_SCORE_MIN
        assert govde["score_max"] == RISK_SURVEY_SCORE_MAX

    def test_yazilan_puan_geri_okunuyor(self, client_for, db_session):
        user = _kullanici(db_session, email="turrr@test.local")
        istemci = client_for(user)

        yazma = istemci.put(
            f"/api/users/{user.id}/risk-survey",
            json={"risk_survey_score": 5},
        )
        assert yazma.status_code == 200
        assert yazma.json()["risk_profile"] == RiskProfile.GROWTH.value

        okuma = istemci.get(f"/api/users/{user.id}/risk-survey")
        assert okuma.json()["risk_survey_score"] == 5
        assert okuma.json()["score_band"] == [5, 5]


def _migration_yolu(dosya_adi: str):
    """Migration dosyasının yolunu bulur — HEM lokal koşumda (`backend/` ve
    `tests/` repo kökünde kardeş klasör) HEM `docker compose exec -w / api
    pytest /tests -q` ile koşulduğunda (compose `./backend:/app` mount eder;
    container'da `/backend` diye bir yol YOKTUR, `backend/` içeriği doğrudan
    `/app` altındadır) doğru sonucu verir.

    2026-08-28: bu iki koşum biçimi arasındaki fark fark edilmeden bu testler
    docker'da FileNotFoundError ile düşüyordu — merge/kod değişikliğiyle
    ilgisi yoktu, salt yol varsayımı tekti.
    """
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    for aday_kok in (
        kok / "backend" / "alembic" / "versions",
        kok / "app" / "alembic" / "versions",
    ):
        aday = aday_kok / dosya_adi
        if aday.exists():
            return aday
    raise FileNotFoundError(
        f"{dosya_adi}: ne backend/alembic/versions ne app/alembic/versions altında bulundu "
        f"(aranan kök: {kok})"
    )


class TestVeritabaniKisiti:
    """CHECK kısıtı hem MODELDE hem MIGRATION'da olmalı.

    `docs/DATA.md` §8: testler migration koşmaz (SQLite +
    `Base.metadata.create_all`), dolayısıyla yalnızca migration'a yazılan bir
    kısıt testlerde hiç sınanmaz; yalnızca modele yazılan ise gerçek
    veritabanında hiç var olmaz. İkisinin ayrışması sessiz bir boşluk açar.
    """

    def test_aralik_disi_puan_veritabani_duzeyinde_reddediliyor(self, db_session):
        """Uygulamayı ATLAYAN bir yol (elle SQL, veri aktarımı) aralık dışı
        puan yazarsa uygunluk kontrolü hak edilmemiş genişlikte tavsiye
        üretirdi. Bu yüzden kısıt üçüncü kez veritabanında da duruyor."""
        from sqlalchemy.exc import IntegrityError

        user = _kullanici(db_session, email="kisit@test.local")
        with pytest.raises(IntegrityError):
            db_session.execute(
                User.__table__.update().where(User.id == user.id).values(risk_survey_score=8)
            )
            db_session.flush()

    def test_migration_ve_model_ayni_kisiti_tasiyor(self):
        """Mekanik ama gerekli: ikisi ayrışırsa kimse fark etmez."""
        migration = _migration_yolu("f18c4a2e7b90_user_risk_survey_score.py").read_text(
            encoding="utf-8"
        )

        kisit = next(
            c for c in User.__table__.constraints if c.name == "ck_users_risk_survey_score_range"
        )
        ifade = str(kisit.sqltext)

        assert kisit.name in migration
        assert ifade in migration, f"model ifadesi migration'da yok: {ifade}"


class TestRiskDegerlendirmesindeTasinmasi:
    """Anket puanı risk değerlendirmesiyle birlikte dönüyor.

    Arayüzdeki "Risk Profili" kartı puanı gösteriyor. Ayrı bir uç çağırmak
    zorunda kalmasın diye `/api/risk/{user_id}` yanıtında `risk_profile`'ın
    yanında taşınıyor — ikisi aynı şeyin iki gösterimi, puan yetkili.
    """

    def test_puan_degerlendirmeyle_birlikte_donuyor(self, db_session):
        from app.models import Portfolio
        from app.services.risk_service import get_risk_assessment

        user = _kullanici(db_session, email="risk-puan@test.local")
        db_session.add(Portfolio(user_id=user.id))
        db_session.commit()
        set_user_risk_survey(db_session, user.id, 5)

        sonuc = get_risk_assessment(db_session, user.id)

        assert sonuc.risk_survey_score == 5
        assert sonuc.risk_profile is RiskProfile.GROWTH

    def test_profil_override_edilince_puan_DUSER(self, db_session):
        """`profile_override` "ya agresif olsaydım?" senaryosudur; o sonuçta
        profil kullanıcının beyanı DEĞİLDİR.

        Puanı yanında taşımak, kullanıcının o puanı verdiğini söylemek
        olurdu — arayüz de onu profil rozetinin altına basardı.
        """
        from app.models import Portfolio
        from app.services.risk_service import get_risk_assessment

        user = _kullanici(db_session, email="risk-override@test.local")
        db_session.add(Portfolio(user_id=user.id))
        db_session.commit()
        set_user_risk_survey(db_session, user.id, 2)

        sonuc = get_risk_assessment(db_session, user.id, profile_override=RiskProfile.AGGRESSIVE)

        assert sonuc.risk_profile is RiskProfile.AGGRESSIVE
        assert sonuc.risk_survey_score is None

    def test_anket_doldurulmamissa_none(self, db_session):
        from app.models import Portfolio
        from app.services.risk_service import get_risk_assessment

        user = _kullanici(db_session, email="risk-anketsiz@test.local")
        db_session.add(Portfolio(user_id=user.id))
        db_session.commit()

        assert get_risk_assessment(db_session, user.id).risk_survey_score is None
