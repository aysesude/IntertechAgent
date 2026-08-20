"""Capraz kontrol: servis katmaninin sayilarini HAM SQL ile dogrular.

Neden: testleri de servisi de ayni kisi yazdiysa, ortak bir yanlis varsayim
ikisinde birden yasar ve test yesil yanar. Buradaki SQL, servis kodunun tek
satirini bile kullanmadan ayni sayilari bagimsiz olarak yeniden hesaplar.
Iki taraf tutmuyorsa ekranda MISMATCH gorunur.

Kullanim:
    docker compose exec -w / api python scripts/capraz_kontrol.py <user_id>
"""

import sys
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text

from app.core.db import SessionLocal
from app.services.portfolio_service import get_holdings_valuation, get_transactions

# En guncel kapanis + kur ile varlik basina TRY deger. Servis kodundan bagimsiz.
SQL_DEGERLEME = text("""
    WITH son_fiyat AS (
        SELECT DISTINCT ON (asset_id) asset_id, close_price
        FROM price_history
        ORDER BY asset_id, price_date DESC
    ),
    kur AS (
        SELECT a.symbol AS kur_sembol, f.close_price AS oran
        FROM assets a
        JOIN son_fiyat f ON f.asset_id = a.id
        WHERE a.symbol IN ('USDTRY', 'EURTRY', 'GBPTRY', 'CHFTRY')
    )
    SELECT
        a.symbol,
        h.quantity,
        h.avg_cost_price,
        f.close_price AS ham_fiyat,
        CASE WHEN a.currency = 'TRY' THEN 1 ELSE k.oran END AS kur
    FROM holdings h
    JOIN assets a ON a.id = h.asset_id
    JOIN portfolios p ON p.id = h.portfolio_id
    LEFT JOIN son_fiyat f ON f.asset_id = a.id
    LEFT JOIN kur k ON k.kur_sembol = a.currency || 'TRY'
    WHERE p.user_id = :user_id
    """)

SQL_NAKIT = text("""
    SELECT COALESCE(SUM(t.cash_amount_try), 0)
    FROM transactions t
    JOIN portfolios p ON p.id = t.portfolio_id
    WHERE p.user_id = :user_id
    """)

SQL_ISLEM_SAYISI = text("""
    SELECT COUNT(*)
    FROM transactions t
    JOIN portfolios p ON p.id = t.portfolio_id
    WHERE p.user_id = :user_id
    """)

SQL_POZISYON = text("""
    SELECT a.symbol,
           SUM(CASE t.transaction_type
                 WHEN 'buy' THEN t.quantity
                 WHEN 'sell' THEN -t.quantity
                 ELSE 0 END) AS miktar
    FROM transactions t
    JOIN portfolios p ON p.id = t.portfolio_id
    JOIN assets a ON a.id = t.asset_id
    WHERE p.user_id = :user_id
    GROUP BY a.symbol
    """)


def _yuvarla(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _karsilastir(etiket: str, sql_degeri, servis_degeri, tolerans=Decimal("0.02")) -> bool:
    if sql_degeri is None or servis_degeri is None:
        tamam = sql_degeri is None and servis_degeri is None
    else:
        tamam = abs(Decimal(sql_degeri) - Decimal(servis_degeri)) <= tolerans
    isaret = "  OK  " if tamam else " MISMATCH "
    print(f"  [{isaret}] {etiket:<34} SQL={sql_degeri!s:>18}  SERVIS={servis_degeri!s:>18}")
    return tamam


def main(user_id_str: str) -> None:
    user_id = UUID(user_id_str)
    db = SessionLocal()
    hatalar = 0
    try:
        rows = db.execute(SQL_DEGERLEME, {"user_id": str(user_id)}).all()
        nakit = Decimal(str(db.execute(SQL_NAKIT, {"user_id": str(user_id)}).scalar_one()))

        sql_degerler: dict[str, Decimal | None] = {}
        sql_maliyetler: dict[str, Decimal] = {}
        toplam_deger = Decimal(0)
        for row in rows:
            maliyet = _yuvarla(Decimal(str(row.quantity)) * Decimal(str(row.avg_cost_price)))
            sql_maliyetler[row.symbol] = maliyet
            if row.ham_fiyat is None or row.kur is None:
                sql_degerler[row.symbol] = None
                continue
            deger = _yuvarla(
                Decimal(str(row.quantity)) * Decimal(str(row.ham_fiyat)) * Decimal(str(row.kur))
            )
            sql_degerler[row.symbol] = deger
            toplam_deger += deger

        payda = toplam_deger + nakit

        print("=" * 90)
        print("1) VARLIK DEGERLEME  (ham SQL  vs  get_holdings_valuation)")
        print("=" * 90)
        print(f"  SQL toplam varlik degeri : {toplam_deger}")
        print(f"  SQL serbest nakit        : {nakit}")
        print(f"  SQL agirlik paydasi      : {payda}")
        print()

        servis = get_holdings_valuation(db, user_id)
        for row in servis.holdings:
            sql_deger = sql_degerler.get(row.symbol)
            hatalar += not _karsilastir(f"{row.symbol} deger", sql_deger, row.market_value_try)
            hatalar += not _karsilastir(
                f"{row.symbol} maliyet", sql_maliyetler.get(row.symbol), row.cost_basis_try
            )
            beklenen_agirlik = (
                _yuvarla(sql_deger / payda * 100) if sql_deger is not None and payda > 0 else None
            )
            hatalar += not _karsilastir(
                f"{row.symbol} agirlik", beklenen_agirlik, row.weight_percent
            )
            beklenen_kz = (
                _yuvarla((sql_deger / sql_maliyetler[row.symbol] - 1) * 100)
                if sql_deger is not None and sql_maliyetler[row.symbol] > 0
                else None
            )
            hatalar += not _karsilastir(
                f"{row.symbol} K/Z %", beklenen_kz, row.unrealized_pnl_percent
            )
            print()

        print("=" * 90)
        print("2) ISLEM DEFTERI  (ham SQL  vs  get_transactions)")
        print("=" * 90)
        sql_adet = db.execute(SQL_ISLEM_SAYISI, {"user_id": str(user_id)}).scalar_one()
        islemler = get_transactions(db, user_id)
        hatalar += not _karsilastir("islem sayisi", sql_adet, len(islemler.transactions))

        # Son pozisyon: SQL toplami ile defter oynatmasinin son degeri ayni olmali.
        sql_pozisyon = {
            row.symbol: _yuvarla(Decimal(str(row.miktar)))
            for row in db.execute(SQL_POZISYON, {"user_id": str(user_id)}).all()
        }
        son_pozisyon: dict[str, Decimal] = {}
        for row in islemler.transactions:
            if row.symbol is not None and row.position_after is not None:
                son_pozisyon[row.symbol] = _yuvarla(row.position_after)
        for symbol in sorted(sql_pozisyon):
            hatalar += not _karsilastir(
                f"{symbol} son pozisyon", sql_pozisyon[symbol], son_pozisyon.get(symbol)
            )

        print()
        print("=" * 90)
        if hatalar:
            print(f"SONUC: {hatalar} uyusmazlik var — sayilar guvenilir DEGIL.")
            sys.exit(1)
        print("SONUC: tum sayilar ham SQL ile birebir tutuyor.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Kullanim: python scripts/capraz_kontrol.py <user_id>")
    main(sys.argv[1])
