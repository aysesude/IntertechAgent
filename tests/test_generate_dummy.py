from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Holding, PriceHistory, User
from data.generate_dummy import (
    MAX_HOLDINGS_PER_USER,
    MIN_HOLDINGS_PER_USER,
    NUM_USERS,
)
from data.generate_dummy import (
    main as generate_dummy_main,
)


def test_generate_dummy_creates_expected_data(engine):
    generate_dummy_main()

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(User)) == NUM_USERS

        holding_counts = (
            session.execute(
                select(func.count()).select_from(Holding).group_by(Holding.portfolio_id)
            )
            .scalars()
            .all()
        )
        assert len(holding_counts) == NUM_USERS
        assert all(MIN_HOLDINGS_PER_USER <= c <= MAX_HOLDINGS_PER_USER for c in holding_counts)

        assert (
            session.scalar(select(func.count()).select_from(Holding).where(Holding.quantity <= 0))
            == 0
        )
        assert (
            session.scalar(
                select(func.count()).select_from(PriceHistory).where(PriceHistory.close_price <= 0)
            )
            == 0
        )


def test_generate_dummy_is_deterministic(engine):
    # Not: asset_id her main() cagrisinda yeniden olusturulan varliklarin
    # seed'lenmemis (uuid.uuid4()) birincil anahtaridir, bu yuzden calismalar
    # arasi kalici degildir; karsilastirma icin varligin sembolu kullanilir.
    generate_dummy_main()
    with Session(engine) as session:
        first_user = session.execute(select(User).order_by(User.email).limit(1)).scalar_one()
        first_run_holdings = sorted(
            (h.asset.symbol, str(h.quantity), str(h.avg_cost_price))
            for h in first_user.portfolio.holdings
        )

    generate_dummy_main()
    with Session(engine) as session:
        same_user = session.execute(select(User).order_by(User.email).limit(1)).scalar_one()
        assert same_user.email == first_user.email
        second_run_holdings = sorted(
            (h.asset.symbol, str(h.quantity), str(h.avg_cost_price))
            for h in same_user.portfolio.holdings
        )

    assert first_run_holdings == second_run_holdings
