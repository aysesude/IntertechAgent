"""Demo kullanıcılarının adı ve e-postası.

NEDEN FAKER DEĞİL. `Faker("tr_TR").name()` ünvanlı ve arkaik adlar üretiyordu
— ölçülen çıktı: "Uz. Zamir Aşıkel Tarhan", "Prof. Ferzi Asım Akdeniz",
"Nazende Şehreban Eraslan Sezgin". Ad, üst çubukta ve baş harf rozetinde HER
sayfada duruyor (`AuthContext.initialsOf`), dolayısıyla bu bir kozmetik ayrıntı
değil: demo videolarında her karede görünen metin.

İkinci sorun: ad ile e-posta birbirinden BAĞIMSIZ üretiliyordu ve tutmuyordu —
`yildirimsatrettin@example.org` ↔ "Uz. Zamir Aşıkel Tarhan". Burada e-posta
addan TÜRETİLİYOR, dolayısıyla profil ekranındaki iki alan birbirini tutuyor.

DEĞİŞMEYENLER. Bu modül yalnızca ad ve e-postayı üretir. Kullanıcı UUID'leri
(`seed_ledger._user_id`) ve T.C. kimlik numaraları (ayrı bir Faker örneği)
buradan etkilenmez — yani ekibin ezberlediği "T.C. no + ortak şifre" giriş
bilgileri seed tazelense de aynı kalır.

DETERMİNİZM. `ad_soyad(i)` saf bir fonksiyondur: rastgelelik yok, sıralama
indekse bağlı. Aynı indeks her koşuda aynı ismi verir.
"""

import unicodedata

# Ad havuzu, kullanıcı sayısından (50 + demo personası) UZUN tutuldu: indeks
# ada birebir eşlendiği için ad tekrarı olmuyor ve dolayısıyla tam ad da
# benzersiz kalıyor. Havuz büyürse NUM_USERS'ı artırmak ek iş gerektirmez.
ADLAR: tuple[str, ...] = (
    "Zeynep",
    "Mert",
    "Elif",
    "Kerem",
    "Defne",
    "Emir",
    "Azra",
    "Yiğit",
    "Nehir",
    "Aras",
    "Duru",
    "Alp",
    "Ada",
    "Poyraz",
    "Ecrin",
    "Kaan",
    "Asya",
    "Ömer",
    "Nisan",
    "Bora",
    "Melis",
    "Sinan",
    "Beren",
    "Tuna",
    "Selin",
    "Onur",
    "Ipek",
    "Barış",
    "Derin",
    "Cem",
    "Lara",
    "Kaya",
    "Naz",
    "Efe",
    "Sude",
    "Burak",
    "Ceren",
    "Deniz",
    "Gökçe",
    "Emre",
    "Irmak",
    "Serkan",
    "Bilge",
    "Tolga",
    "Damla",
    "Hakan",
    "Esra",
    "Volkan",
    "Pınar",
    "Murat",
    "Şeyma",
    "Ufuk",
    "Yasemin",
    "Cenk",
    "Aylin",
    "Berk",
)

# Soyad sayısı ADLAR ile aralarında asal seçildi (53 ile 56): aşağıdaki
# `i * ADIM` yürüyüşü havuzun tamamını dolaşır, ilk elli birde aynı soyad
# arka arkaya iki kez çıkmaz.
SOYADLAR: tuple[str, ...] = (
    "Yılmaz",
    "Kaya",
    "Demir",
    "Şahin",
    "Çelik",
    "Yıldız",
    "Yıldırım",
    "Öztürk",
    "Aydın",
    "Özdemir",
    "Arslan",
    "Doğan",
    "Kılıç",
    "Aslan",
    "Çetin",
    "Kara",
    "Koç",
    "Kurt",
    "Özkan",
    "Şimşek",
    "Polat",
    "Korkmaz",
    "Erdoğan",
    "Aksoy",
    "Bulut",
    "Güneş",
    "Tekin",
    "Yavuz",
    "Bozkurt",
    "Duman",
    "Ateş",
    "Sarı",
    "Bilgin",
    "Ünal",
    "Turan",
    "Acar",
    "Keskin",
    "Işık",
    "Gündoğdu",
    "Uysal",
    "Karaca",
    "Avcı",
    "Toprak",
    "Sezer",
    "Balcı",
    "Güler",
    "Taş",
    "Yalçın",
    "Erdem",
    "Aydemir",
    "Şen",
    "Çakır",
    "Altun",
)

# Soyad yürüyüşünün adımı. ADLAR ile SOYADLAR birbirine yakın uzunlukta
# olduğu için adım 1 olsaydı ad ve soyad aynı hizada ilerler, liste
# "Zeynep Yılmaz / Mert Kaya / Elif Demir" gibi mekanik görünürdü.
ADIM = 7

# Demo kullanıcılarının e-posta alan adı. Gerçek bir alan adı DEĞİL
# (`example.com` ailesi gibi ayrılmış değil ama bize ait de değil) — bu
# adreslere posta gitmez, gitmemeli; yalnızca ekranda ad ile tutarlı
# görünmeleri için var.
EPOSTA_ALAN_ADI = "ornek.com"

# Türkçe harflerin ASCII karşılığı. `unicodedata` ile normalleştirme 'ı' ve
# 'ş' için doğru sonucu vermiyor (birleşik karakter değiller), bu yüzden
# eşleme elle yazılı.
_ASCII_ESLEME = str.maketrans(
    {
        "ç": "c",
        "Ç": "c",
        "ğ": "g",
        "Ğ": "g",
        "ı": "i",
        "I": "i",
        "İ": "i",
        "i": "i",
        "ö": "o",
        "Ö": "o",
        "ş": "s",
        "Ş": "s",
        "ü": "u",
        "Ü": "u",
    }
)


def ad_soyad(index: int) -> str:
    """`index` numaralı demo kullanıcısının tam adı. Saf ve deterministik."""
    ad = ADLAR[index % len(ADLAR)]
    soyad = SOYADLAR[(index * ADIM) % len(SOYADLAR)]
    return f"{ad} {soyad}"


def eposta(full_name: str) -> str:
    """Addan türetilmiş e-posta: 'Zeynep Yılmaz' -> 'zeynep.yilmaz@ornek.com'.

    Ad benzersiz olduğu sürece e-posta da benzersizdir; ayrıca bir tekilleştirme
    adımına gerek yok (bkz. `ADLAR` yorumu).
    """
    parcalar = [
        unicodedata.normalize("NFKD", parca.translate(_ASCII_ESLEME))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        for parca in full_name.split()
    ]
    return ".".join(p for p in parcalar if p) + "@" + EPOSTA_ALAN_ADI
