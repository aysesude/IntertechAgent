"""Varlık evreninin TEK tanım noktası.

`data/seed_assets.py` bu listeyi DB'ye yazar; `providers/registry.py` sağlayıcı
zincirini bu listedeki eşlemeden kurar; sentetik üretici `base_price`'ı buradan
okur. Yeni varlık eklemek = bu listeye bir satır eklemek; başka kod değişmez.

Alan notları:
- `provider_symbol`: birincil kaynaktaki sembol (THYAO -> 'THYAO.IS',
  USDTRY -> EVDS serisi 'TP.DK.USD.S.YTL', TI2 -> TEFAS fon kodu 'TI2').
- `tcmb_code`: today.xml spot kuru için para birimi kodu (yalnızca döviz).
- `yf_symbol`: yedek yfinance sembolü (EVDS anahtarı yoksa tarihsel kur buradan).
- `ons_to_gram`: GC=F gibi ons-USD vadeli fiyatın gram-TRY'ye çevrilmesi
  (ons / 31.1034768 × o günün USDTRY kuru).
- `base_price`: sentetik serinin başlangıç değeri. Tüm varlıklarda dolu ki
  sistem tamamen çevrimdışı da çalışabilsin (A1); gerçek veri geldiğinde
  upsert önceliği sentetiği ezer, tersi asla olmaz.

  **Uydurulmaz, ölçülür.** Fon değerleri bir kez uydurulmuştu ve gerçekten
  kat kat sapıyordu (`TI2` 2,1450 yazılıydı, gerçek fiyatı 0,11 — 20 kat).
  Gerçek verinin bulunduğu ortamda sapma zararsız (upsert onu eziyor), ama
  backfill hiç koşmamış bir kurulumda gerçekle alakasız bir evren üretiyordu.
  Tazelemek için serinin İLK gerçek fiyatı okunur — bugünkü değil, çünkü
  `base_price` serinin başlangıcıdır:

      SELECT a.symbol,
             (SELECT p.close_price FROM price_history p
              WHERE p.asset_id = a.id AND p.source <> 'synthetic'
              ORDER BY p.price_date LIMIT 1) AS ilk_gercek_fiyat
      FROM assets a WHERE a.is_active ORDER BY a.symbol;

  Aşağıdaki TEFAS fon değerleri 21 Ağustos 2026'da bu sorguyla alındı
  (serinin başı: 21 Ağustos 2025). Hisse, maden ve döviz değerleri hâlâ
  elle konmuş yaklaşık değerler; mertebeleri doğru olduğu için
  güncellenmedi.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.config import AssetClass, AssetSubType, PriceSource

TROY_OUNCE_GRAMS = Decimal("31.1034768")


@dataclass(frozen=True)
class AssetSpec:
    symbol: str
    name: str
    asset_class: AssetClass
    base_price: Decimal
    currency: str = "TRY"
    sub_type: AssetSubType | None = None
    data_source: PriceSource = PriceSource.SYNTHETIC
    provider_symbol: str | None = None
    tcmb_code: str | None = None
    yf_symbol: str | None = None
    ons_to_gram: bool = False
    derived_from: str | None = None
    derived_factor: Decimal | None = None
    # Sentetik üretimde sınıf varsayılanını ezen günlük drift/volatilite
    # (bkz. seed_prices_synthetic.ASSET_CLASS_DAILY_DRIFT_VOLATILITY). Yalnızca
    # varlık, sınıfının tipik davranışından ayrıldığında verilir — ör. para
    # piyasası fonu CASH sınıfındadır ama mevduat gibi sabit durmaz, fiyatı
    # üzerinden getiri biriktirir.
    synthetic_daily_drift: float | None = None
    synthetic_daily_volatility: float | None = None
    # Kullanıcı portföyünde TUTULABİLİR mi.
    #
    # Endeksler (XU100) fiyatlanır ve saklanır — kıyaslama onlara dayanıyor —
    # ama satın alınamazlar. Bayrak olmasaydı seed, endeksi sıradan bir hisse
    # gibi kullanıcılara dağıtırdı.
    tradable: bool = True
    # Uygunluk risk seviyesi (1-7), SINIF VARSAYILANINI EZER.
    #
    # `None` ise `ASSET_CLASS_ADVICE_RISK_LEVEL[asset_class]` geçerlidir; o
    # tablo TİPİK varlığı tarif eder. Bu alan yalnızca varlık sınıfından
    # ayrıldığında doldurulur ve iki yöne de gidebilir:
    #
    #   IOO  para piyasası fonu   sınıfı BOND=2, kendisi 1  (aşağı)
    #   AKE  eurobond fonu        sınıfı BOND=2, kendisi 3  (yukarı)
    #   AAPL ABD hissesi          sınıfı STOCK=5, kendisi 6 (yukarı)
    #
    # Neden hesaplanmıyor da elle yazılıyor: hesaplansaydı fiyat geçmişine
    # bağımlı olurdu — geçmişi henüz olmayan yeni varlıkta seviye üretilemez
    # ve tablo risk motorunun volatilite borusuna kenetlenirdi. Uygunluk
    # sıralaması ürün kategorisine bakar, o kategori de zaten burada tanımlı.
    #
    # Okunacak yer: `services/advice_eligibility.asset_risk_level`.
    risk_level: int | None = None


def _stock(symbol: str, name: str, base_price: str) -> AssetSpec:
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.STOCK,
        base_price=Decimal(base_price),
        data_source=PriceSource.YFINANCE,
        provider_symbol=f"{symbol}.IS",
    )


def _foreign_stock(symbol: str, name: str, base_price: str) -> AssetSpec:
    """ABD hissesi. `_stock`'tan iki farkı var ve ikisi de önemli.

    Sembole `.IS` EKLENMEZ: yfinance'ta ABD hisseleri sade koduyla geçer.

    Para birimi USD: değerleme `valuation_service` içinde O GÜNÜN kuruyla
    TRY'ye çevrilir (AK 5.7). Bu yol daha önce yalnızca `AKE` (eurobond fonu)
    tarafından kullanılıyordu — `docs/DATA.md` onu "evrendeki tek TRY dışı
    varlık" diye anıyordu; artık yirmi iki varlık bu yoldan geçiyor.

    Uygunluk seviyesi 6, yani yerli hissenin (STOCK=5) bir üstü. Gerekçe
    volatilite DEĞİL — ölçüm tersini söylüyor, ABD ortalaması %28,8'e karşı
    BIST %38,6 — sınır ötesi erişimin kendisi: kur maruziyeti, saklama,
    yerel yatırımcı korumasının bulunmaması, farklı vergi rejimi.
    """
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.STOCK,
        base_price=Decimal(base_price),
        currency="USD",
        data_source=PriceSource.YFINANCE,
        provider_symbol=symbol,
        risk_level=6,
    )


def _fx(symbol: str, name: str, tcmb_code: str, base_price: str) -> AssetSpec:
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.CURRENCY,
        base_price=Decimal(base_price),
        data_source=PriceSource.TCMB_EVDS,
        provider_symbol=f"TP.DK.{tcmb_code}.S.YTL",
        tcmb_code=tcmb_code,
        yf_symbol=f"{tcmb_code}TRY=X",
    )


def _gram_metal(
    symbol: str,
    name: str,
    yf_future: str,
    base_price: str,
    risk_level: int | None = None,
) -> AssetSpec:
    """Ons vadeli fiyattan türetilen gram metal.

    `risk_level`: kıymetli maden sınıfı uygunlukta 4'tür ama sınıf içi
    dağılım geniş — ölçüldü (365 gün, 26 Ağustos 2026): gram altın %28,6,
    gümüş %65,9, platin %55,3. Gümüş ve platin YERLİ HİSSENİN (%38,6,
    seviye 5) üstünde oynuyor, dolayısıyla ondan düşük bir kademede
    duramazlar. Bu ikisi sanayi/spekülatif metal; perakende yatırımcının
    "altın alıyorum" refleksiyle aynı yere konmaları yanlış olurdu.
    """
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.PRECIOUS_METAL,
        base_price=Decimal(base_price),
        data_source=PriceSource.YFINANCE,
        provider_symbol=yf_future,
        ons_to_gram=True,
        risk_level=risk_level,
    )


def _gold_coin(symbol: str, name: str, factor: str, base_price: str) -> AssetSpec:
    # Katsayı = sikke ağırlığı (g) × milyem. Çeyrek: 1.75 × 0.916 = 1.6030.
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=AssetClass.PRECIOUS_METAL,
        base_price=Decimal(base_price),
        sub_type=AssetSubType.GOLD_COIN,
        data_source=PriceSource.DERIVED,
        derived_from="XAUTRY",
        derived_factor=Decimal(factor),
    )


# Fon alt türü -> varlık sınıfı. Fonun ekonomik riski neyse sınıfı odur:
# para piyasası fonu nakit gibi, altın fonu altın gibi, borçlanma araçları
# fonu tahvil gibi davranır.
#
# Eskiden tüm fonlar AssetClass.STOCK idi ("gerek.md §2 fonları hisse senedi
# başlığı altında gruplar" gerekçesiyle). §2'nin listesi sınıf başına kendi
# enstrümanlarını sayıyor ("Kıymetli Madenler (Altın, Gümüş, Platin)"), yani
# "(Hisse, Fon)" ifadesi HİSSE fonunu kastediyor. Kuralı harfi harfine
# uygulamak altın fonuna ve para piyasası fonuna FR-4'ün "Hisse -> Yüksek"
# risk etiketini düşürüyordu; para piyasası fonu en düşük riskli
# enstrümandır, risk motorunda savunma tarafında (BOND+CASH) sayılmalıdır.
_FUND_ASSET_CLASS: dict[AssetSubType, AssetClass] = {
    AssetSubType.EQUITY_FUND: AssetClass.STOCK,
    # Serbest fon sınıfı da İÇERİĞİNDEN çıkar, kabuğundan değil: evrendeki
    # tek serbest fon (BHE) hisse senedi yoğun olduğu için STOCK. Bir gün
    # para piyasası serbest fonu eklenirse alt türü MONEY_MARKET_FUND
    # olur ve `risk_level=7` ile işaretlenir — yani 7'yi veren yapı,
    # sınıfı veren içeriktir; ikisi ayrı alanlarda durur.
    AssetSubType.HEDGE_FUND: AssetClass.STOCK,
    # Para piyasası fonu artık CASH DEĞİL, BOND.
    #
    # `AssetClass.CASH` yalnızca SERBEST NAKDİ (defterdeki bakiye, harcanabilir
    # para) temsil ediyor. Para piyasası fonu ise bir yatırımdır: fiyatı vardır
    # ve oynar (ölçülen: İş Portföy para piyasası fonu %1,42 yıllık volatilite),
    # takas süresi vardır. Nakit dilimine konulması "bu para elimde" demek olur
    # ki değildir; portföyü olduğundan likit ve güvenli gösterirdi.
    #
    # Kısa vadeli borçlanma araçları ve repo tuttuğu için sabit getirili
    # tarafa, yani BOND'a düşüyor. Risk motorunun savunma tabanı zaten
    # BOND+CASH toplamına bakıyor, dolayısıyla o taraf etkilenmiyor.
    AssetSubType.MONEY_MARKET_FUND: AssetClass.BOND,
    AssetSubType.GOLD_FUND: AssetClass.PRECIOUS_METAL,
    AssetSubType.BOND_FUND: AssetClass.BOND,
    AssetSubType.CORPORATE_BOND_FUND: AssetClass.BOND,
    AssetSubType.EUROBOND_FUND: AssetClass.BOND,
}


def _fund(
    symbol: str,
    name: str,
    sub_type: AssetSubType,
    base_price: str,
    currency: str = "TRY",
    synthetic_daily_drift: float | None = None,
    synthetic_daily_volatility: float | None = None,
    risk_level: int | None = None,
) -> AssetSpec:
    """TEFAS fonu. Sembol = fon kodu = sağlayıcı sembolü.

    `currency`: TEFAS fiyatları kural olarak TL'dir; döviz cinsi fonlarda
    (ör. AKE eurobond fonu) birim fiyat kendi para biriminde yayımlanır ve
    değerleme o günün kuruyla TRY'ye çevrilir (AK 5.7).

    `risk_level`: fon, sınıfının tipik seviyesinden ayrılıyorsa verilir.
    Kullanıcının kararı: "fonlar kendi risklerini taşısın" — bir fonun
    uygunluk seviyesi kabuğundan (BOND/STOCK) değil, İÇERİĞİNDEN çıkar.
    Para piyasası fonu da eurobond fonu da BOND sınıfındadır ama biri
    seviye 1, diğeri 3'tür.
    """
    return AssetSpec(
        symbol=symbol,
        name=name,
        asset_class=_FUND_ASSET_CLASS[sub_type],
        base_price=Decimal(base_price),
        currency=currency,
        sub_type=sub_type,
        risk_level=risk_level,
        data_source=PriceSource.TEFAS,
        provider_symbol=symbol,
        synthetic_daily_drift=synthetic_daily_drift,
        synthetic_daily_volatility=synthetic_daily_volatility,
    )


ASSET_UNIVERSE: list[AssetSpec] = [
    # --- Endeks (kıyaslama için; tutulamaz) ---
    #
    # `get_benchmark_comparison` BIST 100'ü hep istiyordu ama evrende karşılığı
    # yoktu: varlık bulunamayınca kıyas listesinden SESSİZCE düşüyordu.
    # Ölçülen sonuç (23 Ağustos test turu): "Portföyüm BIST 100'e göre nasıl?"
    # sorusuna altın ve dolar karşılaştırması dönüyor, endeksten hiç söz
    # edilmiyordu — sorulan şey cevaplanmadan.
    #
    # base_price uydurma değil, ölçülmüş: 21.08.2025 kapanışı (yfinance).
    AssetSpec(
        symbol="XU100",
        name="BIST 100",
        asset_class=AssetClass.STOCK,
        base_price=Decimal("11313.90"),
        data_source=PriceSource.YFINANCE,
        provider_symbol="XU100.IS",
        tradable=False,
    ),
    # --- Hisse: BIST 100 endeksinin TAMAMI (yfinance) ---
    #
    # `base_price` değerlerinin hepsi ÖLÇÜLDÜ (25 Ağustos 2026, serinin ilk
    # gerçek günü) — eskiden buradaki 15 hisse "285.00", "62.50" gibi
    # yuvarlanmış tahminler taşıyordu, oysa depo kuralı ölçülmüş değer istiyor
    # (bkz. docs/DATA.md "base_price uydurulmaz, ölçülür"). Fonlarda uygulanan
    # kural artık hisselerde de geçerli.
    #
    # base_price yalnızca ÇEVRİMDIŞI sentetik seriyi başlatmak için kullanılır;
    # gerçek veri geldiğinde upsert onu ezer.
    _stock("AKBNK", "Akbank", "70.500000"),
    _stock("AKSA", "Aksa Akrilik", "10.830000"),
    _stock("AKSEN", "Aksa Enerji", "40.720001"),
    _stock("ALARK", "Alarko Holding", "92.199997"),
    _stock("ALTNY", "Altınay Savunma", "18.117647"),
    _stock("ANSGR", "Anadolu Sigorta", "22.580000"),
    _stock("AEFES", "Anadolu Efes", "17.510000"),
    _stock("ARCLK", "Arçelik", "142.300003"),
    _stock("ASELS", "Aselsan", "185.500000"),
    _stock("ASTOR", "Astor Enerji", "116.300003"),
    _stock("BALSU", "Balsu Gıda", "26.660000"),
    _stock("BTCIM", "Batıçim", "4.140000"),
    _stock("BSOKE", "Batısöke Çimento", "14.610000"),
    _stock("BERA", "Bera Holding", "18.120001"),
    _stock("BIMAS", "BİM Mağazalar", "268.000000"),
    _stock("BRSAN", "Borusan Boru", "479.000000"),
    _stock("BRYAT", "Borusan Yatırım", "2847.500000"),
    _stock("CCOLA", "Coca-Cola İçecek", "51.500000"),
    _stock("CWENE", "CW Enerji", "17.991449"),
    _stock("CANTE", "Çan2 Termik", "2.650000"),
    _stock("CIMSA", "Çimsa", "50.549999"),
    _stock("DAPGM", "DAP Gayrimenkul", "17.000000"),
    _stock("DSTKF", "Destek Faktoring", "645.500000"),
    _stock("DOHOL", "Doğan Holding", "19.299999"),
    _stock("DOAS", "Doğuş Otomotiv", "196.000000"),
    _stock("EFOR", "Efor Yatırım", "19.283333"),
    _stock("ECILC", "Eczacıbaşı İlaç", "63.200001"),
    _stock("EKGYO", "Emlak Konut GYO", "21.040001"),
    _stock("ENJSA", "Enerjisa Enerji", "75.500000"),
    _stock("ENERY", "Enerya Enerji", "10.360000"),
    _stock("ENKAI", "Enka İnşaat", "73.250000"),
    _stock("EREGL", "Ereğli Demir Çelik", "29.680000"),
    _stock("ESEN", "Esenboğa Elektrik", "9.720000"),
    _stock("EUREN", "Europen Endüstri", "7.900000"),
    _stock("EUPWR", "Europower Enerji", "30.000000"),
    _stock("FROTO", "Ford Otosan", "118.300003"),
    _stock("GSRAY", "Galatasaray Sportif", "1.690000"),
    _stock("GENIL", "Gen İlaç", "14.046666"),
    _stock("GESAN", "Girişim Elektrik", "49.900002"),
    _stock("GRTHO", "GrainTurk Holding", "456.000000"),
    _stock("GUBRF", "Gübre Fabrikaları", "295.000000"),
    _stock("GLRMK", "Gülermak", "166.800003"),
    _stock("GRSEL", "Gür-Sel Turizm", "337.000000"),
    _stock("SAHOL", "Sabancı Holding", "98.050003"),
    _stock("HEKTS", "Hektaş", "4.750000"),
    _stock("IEYHO", "Işıklar Enerji", "15.680000"),
    _stock("ISMEN", "İş Yatırım", "43.040001"),
    _stock("IZENR", "İzdemir Enerji", "9.260000"),
    _stock("KRDMD", "Kardemir (D)", "30.480000"),
    _stock("KTLEV", "Katılımevim", "3.344528"),
    _stock("KLRHO", "Kiler Holding", "67.250000"),
    _stock("KCHOL", "Koç Holding", "190.399994"),
    _stock("KUYAS", "Kuyaş Yatırım", "59.000000"),
    _stock("MAGEN", "Margün Enerji", "20.120001"),
    _stock("MAVI", "Mavi Giyim", "44.000000"),
    _stock("MIATK", "Mia Teknoloji", "41.459999"),
    _stock("MGROS", "Migros", "495.250000"),
    _stock("MPARK", "MLP Sağlık", "370.500000"),
    _stock("OBAMS", "Oba Makarnacılık", "8.566666"),
    _stock("ODAS", "Odaş Elektrik", "6.450000"),
    _stock("ODINE", "Odine Solutions", "146.399994"),
    _stock("OTKAR", "Otokar", "574.000000"),
    _stock("OYAKC", "Oyak Çimento", "25.680000"),
    _stock("PASEU", "Pasifik Eurasia", "110.000000"),
    _stock("PSGYO", "Pasifik GYO", "2.880000"),
    _stock("PAHOL", "Pasifik Holding", "1.650000"),
    _stock("PATEK", "Pasifik Teknoloji", "24.900000"),
    _stock("PGSUS", "Pegasus", "258.000000"),
    _stock("PETKM", "Petkim", "21.580000"),
    _stock("QUAGR", "Qua Granite", "7.510000"),
    _stock("RALYH", "Ral Yatırım Holding", "133.699997"),
    _stock("REEDR", "Reeder Teknoloji", "10.560000"),
    _stock("SARKY", "Sarkuysan", "12.492000"),
    _stock("SASA", "Sasa Polyester", "5.160000"),
    _stock("SKBNK", "Şekerbank", "7.570000"),
    _stock("SOKM", "Şok Marketler", "41.299999"),
    _stock("TAVHL", "TAV Havalimanları", "259.500000"),
    _stock("TKFEN", "Tekfen Holding", "113.000000"),
    _stock("TOASO", "Tofaş", "253.250000"),
    _stock("TRMET", "TR Anadolu Metal", "78.000000"),
    _stock("TRENJ", "TR Doğal Enerji", "58.299999"),
    _stock("TUKAS", "Tukaş Gıda", "3.150000"),
    _stock("TCELL", "Turkcell", "99.800003"),
    _stock("TUPRS", "Tüpraş", "171.600006"),
    _stock("TRALT", "Türk Altın", "24.860001"),
    _stock("THYAO", "Türk Hava Yolları", "343.500000"),
    _stock("GARAN", "Garanti BBVA", "148.800003"),
    _stock("HALKB", "Halkbank", "28.040001"),
    _stock("ISCTR", "İş Bankası (C)", "15.310000"),
    _stock("TSKB", "TSKB", "14.310000"),
    _stock("TURSG", "Türkiye Sigorta", "4.950000"),
    _stock("SISE", "Şişecam", "42.060001"),
    _stock("VAKBN", "VakıfBank", "29.780001"),
    _stock("TTKOM", "Türk Telekom", "61.400002"),
    _stock("ULKER", "Ülker Bisküvi", "118.599998"),
    _stock("VESTL", "Vestel", "40.680000"),
    _stock("YKBNK", "Yapı Kredi Bankası", "34.080002"),
    _stock("ZOREN", "Zorlu Enerji", "4.100000"),
    # --- Hisse: ABD (yfinance, USD) ---
    #
    # Kapsam dosyası (`agents/scope.yaml`) NASDAQ / S&P 500 / Dow Jones'u
    # kapsam içi sayıyor ama evrende bir tane bile yoktu.
    #
    # base_price hepsi ÖLÇÜLDÜ (26 Ağustos 2026, serinin ilk gerçek günü) ve
    # 21 sembolün tamamı açıklanmayan kopukluk için tarandı — hiç çıkmadı.
    # ABD tarafında kurumsal olay verisi eksiksiz; BIST'te FENER/CVKMD'yi
    # dışarıda bırakmak zorunda kaldığımız durumun karşılığı burada çıkmadı.
    #
    # Ölçek burada GERÇEKTEN ayrışıyor: BRK-B %14,7 (SRRI 5), KO/PG/MCD ~%19
    # (6), AMD %72,1 (7). Yerli hissede on beşinin on beşi de 7 alıyordu.
    _foreign_stock("AAPL", "Apple", "230.490005"),  # vol %25,1, SRRI 7
    _foreign_stock("MSFT", "Microsoft", "506.739990"),  # vol %32,4, SRRI 7
    _foreign_stock("NVDA", "NVIDIA", "181.600006"),  # vol %37,0, SRRI 7
    _foreign_stock("GOOGL", "Alphabet", "207.479996"),  # vol %32,7, SRRI 7
    _foreign_stock("AMZN", "Amazon", "229.119995"),  # vol %34,5, SRRI 7
    _foreign_stock("META", "Meta Platforms", "747.380005"),  # vol %38,9, SRRI 7
    _foreign_stock("TSLA", "Tesla", "349.600006"),  # vol %46,7, SRRI 7
    _foreign_stock("AMD", "AMD", "167.130005"),  # vol %72,1, SRRI 7
    _foreign_stock("JPM", "JPMorgan Chase", "299.279999"),  # vol %22,4, SRRI 6
    _foreign_stock("V", "Visa", "350.350006"),  # vol %22,2, SRRI 6
    _foreign_stock("MA", "Mastercard", "590.659973"),  # vol %22,6, SRRI 6
    _foreign_stock("BRK-B", "Berkshire Hathaway", "495.720001"),  # vol %14,7, SRRI 5
    _foreign_stock("JNJ", "Johnson & Johnson", "176.789993"),  # vol %18,8, SRRI 6
    _foreign_stock("LLY", "Eli Lilly", "734.169983"),  # vol %35,8, SRRI 7
    _foreign_stock("UNH", "UnitedHealth", "303.880005"),  # vol %35,7, SRRI 7
    _foreign_stock("KO", "Coca-Cola", "68.830002"),  # vol %18,8, SRRI 6
    _foreign_stock("PG", "Procter & Gamble", "156.960007"),  # vol %19,6, SRRI 6
    _foreign_stock("WMT", "Walmart", "96.080002"),  # vol %26,0, SRRI 7
    _foreign_stock("MCD", "McDonald's", "311.429993"),  # vol %18,4, SRRI 6
    _foreign_stock("XOM", "Exxon Mobil", "112.750000"),  # vol %25,6, SRRI 7
    _foreign_stock("CAT", "Caterpillar", "432.670013"),  # vol %39,9, SRRI 7
    # FENER ve CVKMD BİLEREK DIŞARIDA.
    #
    # İkisinin de fiyat serisinde GERÇEK OLMAYAN bir çöküş var:
    #   FENER  26.12.2025:  9,54 -> 29.12.2025:  3,46  (-%63,7)
    #   CVKMD  31.07.2026: 37,82 -> 03.08.2026: 14,42  (-%61,9)
    #
    # Bu bir değer kaybı değil, sermaye artırımı: fiyat bölünür ama yatırımcının
    # ADEDİ artar, serveti değişmez. yfinance bunu normalde düzeltiyor (BIMAS
    # 14.05.2026'da ikiye bölündü, seride hiç kopukluk yok) ama bu iki şirket
    # için kurumsal olay kaydı EKSİK — FENER'in bilinen bölünmeleri 2005'te
    # bitiyor, CVKMD'nin Ağustos 2026 işlemi hiç kayıtlı değil.
    #
    # Ölçülen hasar: volatilite FENER'de %53,6 yerine %83,0, CVKMD'de %59,8
    # yerine %86,3 çıkıyor. Asıl sorun K/Z'de: bölünme öncesi alıp tutan
    # kullanıcı defterde eski adetle duruyor, yeni fiyatla değerleniyor ve
    # portföyü %64 erimiş görünüyor — oysa hiçbir şey kaybetmemiş.
    #
    # Tüm BIST 100 tarandı: yalnızca bu iki olay var (diğer 8 bölünme sorunsuz
    # düzeltilmiş). İki hisse için elle bölünme kaydı tutmak ya da ">%50 düşüş
    # = bölünme" gibi bir sezgisel yazmak (gerçekten çöken bir hisseyi bölünme
    # sanma riski) kazandırdığından fazlasını götürürdü. 98 hisse yeterli;
    # bilerek bozuk veri dağıtmaktansa dışarıda bırakmak doğru.
    # --- Kıymetli maden: gram fiyatlar (ons vadeli × USDTRY) ---
    # Gram altın sınıf varsayılanında (4) kalır: ölçülen %28,6, gram altından
    # türetilen sikkelerle ve altın fonuyla (%25,6) aynı mertebede.
    _gram_metal("XAUTRY", "Gram Altın", "GC=F", "2450.00"),
    # Gümüş ve platin 5'e çekildi — gerekçe `_gram_metal` docstring'inde.
    _gram_metal("XAGTRY", "Gram Gümüş", "SI=F", "38.00", risk_level=5),
    _gram_metal("XPTTRY", "Gram Platin", "PL=F", "1550.00", risk_level=5),
    # --- Kıymetli maden: sikke (gram altından türetilir) ---
    _gold_coin("CEYREK", "Çeyrek Altın", "1.6030", "4020.00"),
    _gold_coin("YARIM", "Yarım Altın", "3.2060", "8040.00"),
    _gold_coin("TAMALTIN", "Tam Altın", "6.4120", "16080.00"),
    _gold_coin("CUMHUR", "Cumhuriyet Altını", "6.6150", "16500.00"),
    # --- Döviz (tarihsel: EVDS, yedek yfinance; spot: today.xml) ---
    _fx("USDTRY", "Amerikan Doları", "USD", "34.20"),
    _fx("EURTRY", "Euro", "EUR", "37.10"),
    _fx("GBPTRY", "İngiliz Sterlini", "GBP", "43.50"),
    _fx("CHFTRY", "İsviçre Frangı", "CHF", "38.90"),
    # --- Tahvil: TEFAS borçlanma araçları fonları ---
    # Türk tahvillerinin ücretsiz ve güvenilir bir fiyat kaynağı yok. Önceki
    # sürümde burada dört UYDURMA enstrüman vardı (TRT101/TRT052/EUROBOND1/
    # OST2027); gerçek bir ISIN'e karşılık gelmedikleri için hiçbir sağlayıcı
    # onları çekemiyordu ve fiyatları sonsuza kadar sentetik kalıyordu —
    # portföyün ~%21'i bayat veriyle değerleniyor, tahvil volatilitesi son
    # pencerede sıfır çıkıp riski olduğundan düşük gösteriyordu.
    #
    # Yerlerine aynı riski taşıyan GERÇEK TEFAS fonları kondu: günlük fiyat,
    # resmî kaynak (AK 5.1), zaten çalışan TefasProvider. Fon tahvil değildir
    # (vadesi/kuponu yok, yönetim ücreti var) ama tahvil riski taşır ve
    # uydurma enstrümandan her koşulda daha dürüsttür.
    _fund(
        "AK2", "Ak Portföy Uzun Vadeli Borçlanma Araçları Fonu", AssetSubType.BOND_FUND, "0.435853"
    ),
    _fund(
        "APT", "Ak Portföy Orta Vadeli Borçlanma Araçları Fonu", AssetSubType.BOND_FUND, "0.122145"
    ),
    # Birim fiyatı USD yayımlanır; ölçüldü (getiri korelasyonu USDTRY ile
    # -0.11, TL fiyatlı olsaydı ~0.8 beklenirdi). Evrendeki tek TRY dışı
    # varlık, dolayısıyla AK 5.7 kur dönüşümünü egzersiz eden tek enstrüman.
    _fund(
        "AKE",
        "Ak Portföy Eurobond (ABD Doları) Borçlanma Araçları Fonu",
        AssetSubType.EUROBOND_FUND,
        "0.430407",
        currency="USD",
        # Sınıfı BOND (=2) ama uygunluk açısından DÖVİZ ürünüdür: TL'li
        # yatırımcı için getirisinin büyük kısmı kurdan gelir. Bu yüzden
        # döviz kademesinde (3), TL borçlanma fonlarının bir üstünde.
        risk_level=3,
    ),
    _fund(
        "AYR",
        "Ak Portföy Özel Sektör Borçlanma Araçları (TL) Fonu",
        AssetSubType.CORPORATE_BOND_FUND,
        "0.095774",
    ),
    # --- TEFAS fonları ---
    _fund("TI2", "İş Portföy Hisse Senedi Fonu", AssetSubType.EQUITY_FUND, "0.110169"),
    # Adlar TEFAS'taki resmî unvanlarla doğrulandı (25 Ağustos 2026).
    # TCD İş Portföy DEĞİL Tacirler Portföy'ün; AFT ise yurt dışı hisse
    # senedi fonu — yerli/yabancı ayrımı yapılırken bu fark önemli.
    _fund("TCD", "Tacirler Portföy Değişken Fon", AssetSubType.EQUITY_FUND, "35.646015"),
    _fund(
        "AFT",
        "Ak Portföy Yeni Teknolojiler Yabancı Hisse Senedi Fonu",
        AssetSubType.EQUITY_FUND,
        "0.669568",
        # YABANCI hisse fonu: içeriği yurt dışı hisse, dolayısıyla yabancı
        # hisse kademesinde (6). TI2 ve TCD yerli olduğu için 5'te (sınıf
        # varsayılanı) kalır. Fonun kabuğu ikisinde de aynı — ayrımı yapan
        # içeriktir.
        risk_level=6,
    ),
    # PPF KALDIRILDI, yerine IOO geldi.
    #
    # `PPF` kodu "Para Piyasası Fonu" diye okunmuş ama TEFAS kodları anlamlı
    # kısaltmalar değil, keyfi üç harf: o kod AZİMUT PORTFÖY AKÇE SERBEST
    # FON'a ait. Yani etiket, alt tür ve sentetik kalibrasyon bir para piyasası
    # fonunu tarif ederken veri bambaşka bir fondan geliyordu. Ölçüldü:
    # %5,3 yıllık volatilite — para piyasası fonu ~%1,4 mertebesindedir.
    #
    # Serbest fon ayrıca kaldıraç ve türev kullanabilir; `scope.yaml` bu
    # araçları kapsam dışı sayıyor.
    #
    # IOO gerçek bir para piyasası fonu (İş Portföy İkinci Para Piyasası TL).
    # Ölçülen: 250 günlük kesintisiz veri, SIFIR bozuk satır, %1,42 yıllık
    # volatilite (SRRI 2), yıllık %45,8 getiri.
    #
    # Sentetik parametreler çevrimdışı mod içindir: getirisini FİYATI üzerinden
    # biriktirir, sınıf varsayılanıyla düz çizgi kalırdı.
    # Günlük drift 0.00152 ≈ yıllık %46; volatilite 0.0009 ≈ yıllık %1,4.
    _fund(
        "IOO",
        "İş Portföy İkinci Para Piyasası (TL) Fonu",
        AssetSubType.MONEY_MARKET_FUND,
        # Uydurma değil, ölçülmüş: serinin ilk gerçek günü 25.08.2025 kapanışı.
        "3.154068",
        synthetic_daily_drift=0.00152,
        synthetic_daily_volatility=0.0009,
        # Sınıfı BOND (=2) ama uygunluk açısından NAKİT eşdeğeri: kısa vadeli
        # borçlanma aracı ve repo tutar, ölçülen volatilitesi %1,42. En düşük
        # anket puanına sahip kullanıcının alabileceği tek yatırım aracı
        # olması bilinçli — aksi hâlde 1 puanlık kullanıcıya önerilebilecek
        # HİÇBİR varlık kalmıyordu (CASH sınıfında varlık yok).
        risk_level=1,
    ),
    _fund("GTA", "Garanti Portföy Altın Fonu", AssetSubType.GOLD_FUND, "1.078670"),
    # Ölçeğin tepesi: evrendeki TEK serbest fon.
    #
    # Ölçüldü (26 Ağustos 2026): 256 gün kesintisiz veri, açıklanmayan
    # sıçrama YOK, %22,8 yıllık volatilite. base_price serinin ilk gerçek
    # günü (20.08.2025) kapanışı.
    #
    # Seviyesi 7 çünkü SERBEST fondur (nitelikli yatırımcı, portföy
    # sınırlamalarından muafiyet, kaldıraç/açığa satış izni) — içeriği
    # hisse olduğu için değil. Gerekçenin tamamı config.py'de.
    #
    # Rakamı da aynı yöne bakıyor (%22,8, ABD hisseleriyle aynı bantta),
    # yani ölçeğin tepesinde ters bir görüntü oluşmuyor. Aday havuzundaki
    # arbitraj fonları (%2,1-4,7) bu yüzden seçilmedi.
    _fund(
        "BHE",
        "Ak Portföy Birinci Hisse Senedi Serbest Fon",
        AssetSubType.HEDGE_FUND,
        "1.451871",
        risk_level=7,
    ),
    # --- Nakit ---
    #
    # `AssetClass.CASH` altında VARLIK YOK, bilerek. Nakit artık yalnızca
    # defterdeki serbest bakiyedir: alım/satım için elde duran para. O bakiye
    # `ledger_service.cash_balance_as_of` ile hesaplanıp portföy özetinde
    # doğrudan nakit dilimine ekleniyor (portfolio_service), yani temsil etmek
    # için sentetik bir varlığa gerek yok.
    #
    # Mevduat varlıkları (MEVDUAT-V / MEVDUAT-VS) kaldırıldı. Birim fiyatı
    # sabit 1 TL olan, çekilecek piyasa fiyatı bulunmayan bu iki kayıt
    # evrendeki SON sentetik varlıklardı; kaldırılmalarıyla evren tamamen
    # gerçek kaynaklı hâle geldi (AK 5.1).
    #
    # KAPSAM NOTU: `gerek.md` §2 varlık sınıfları arasında "Nakit (Vadeli,
    # Vadesiz mevduat)" diyor, dolayısıyla bu bir sapmadır ve analist onayına
    # sunulmalıdır. Kararın dayanağı: `scope.yaml` mevduatı ZATEN iki ayrı
    # listede kapsam dışı sayıyor (`sabit_getirili` ve `bankacilik_urunleri`),
    # yani sohbet "vadeli mevduat nedir" sorusunu reddederken portföy mevduat
    # tutuyordu. Kaldırma bu çelişkiyi gideriyor.
    #
    # Bedeli: `TransactionType.INTEREST` demoda yalnızca mevduat faizinden
    # üretiliyordu, artık üretilmiyor.
]

SPEC_BY_SYMBOL: dict[str, AssetSpec] = {spec.symbol: spec for spec in ASSET_UNIVERSE}

assert len(SPEC_BY_SYMBOL) == len(ASSET_UNIVERSE), "Varlık evreninde tekrar eden sembol var"


# --- Canlı makro haber eşlemesi (2026-08-25 eki, bkz. app/services/ ---
# macro_news_ingest.py) --------------------------------------------------
#
# yfinance'in ücretsiz `.news` özelliği yalnızca GERÇEK bir Yahoo ticker'ı
# olan sembollerde çalışır. Bu iki fonksiyon "hangi ticker'a haber isteği
# atılır" (yfinance_news_ticker) ile "sonuç hangi iç sembol altında
# saklanır/sorgulanır" (macro_news_key) sorularını AYRI tutar, çünkü
# türetilmiş varlıkların (çeyrek altın vb.) kendi ticker'ı yok — kaynağının
# (gram altın) haberini PAYLAŞIR. İkisi de aynı eşlemeyi kullanmalı: biri
# yazarken (macro_news_ingest), diğeri okurken (risk_agent) — aksi hâlde
# yazılan anahtar hiçbir zaman okunmaz.


def yfinance_news_ticker(spec: AssetSpec) -> str | None:
    """Bu varlık için haber isteği atılacak GERÇEK Yahoo ticker'ı, yoksa
    `None` (ör. Hisse — zaten `get_portfolio_news` ile sembol bazlı
    kapsanıyor; Tahvil/Nakit — TEFAS fonlarının/mevduatın Yahoo'da karşılığı
    yok).

    Döviz için `provider_symbol` DEĞİL `yf_symbol` kullanılır: `provider_symbol`
    EVDS seri kodudur (ör. 'TP.DK.USD.S.YTL'), Yahoo ticker'ı değil.

    İki ayrı "kendi ticker'ı yok, bir TABANIN haberini paylaşır" durumu var:
    türetilmiş sikkeler (`derived_from`, ör. CEYREK -> XAUTRY) VE TEFAS
    üzerinden fiyatlanan altın fonu (GTA, `sub_type=GOLD_FUND`) — ikisi de
    ekonomik riski gram altınla birebir aynı olduğu için XAUTRY'nin
    ticker'ını (GC=F) paylaşır."""
    if spec.asset_class == AssetClass.CURRENCY:
        return spec.yf_symbol
    if spec.asset_class == AssetClass.PRECIOUS_METAL:
        if spec.data_source == PriceSource.YFINANCE and spec.provider_symbol:
            return spec.provider_symbol
        base_symbol = None
        if spec.data_source == PriceSource.DERIVED and spec.derived_from:
            base_symbol = spec.derived_from
        elif spec.sub_type == AssetSubType.GOLD_FUND:
            base_symbol = "XAUTRY"
        if base_symbol:
            base = SPEC_BY_SYMBOL.get(base_symbol)
            return yfinance_news_ticker(base) if base else None
    return None


def macro_news_key(spec: AssetSpec) -> str | None:
    """Bu varlığın canlı haberinin `macro_news_snapshot`ta hangi iç sembol
    altında durduğu/aranacağı. `yfinance_news_ticker(spec)` `None` dönüyorsa
    bu da `None` döner — anlamsız bir anahtar üretilmez.

    Kendi ticker'ı olmayıp bir tabanın haberini paylaşan varlıklar (türetilmiş
    sikkeler VE GTA altın fonu — bkz. `yfinance_news_ticker`) kendi sembolleri
    DEĞİL, o tabanın sembolü altında saklanır — aynı haberin birden fazla
    kopyası çekilmesin diye."""
    if yfinance_news_ticker(spec) is None:
        return None
    if spec.data_source == PriceSource.DERIVED and spec.derived_from:
        return spec.derived_from
    if spec.asset_class == AssetClass.PRECIOUS_METAL and spec.sub_type == AssetSubType.GOLD_FUND:
        return "XAUTRY"
    return spec.symbol
