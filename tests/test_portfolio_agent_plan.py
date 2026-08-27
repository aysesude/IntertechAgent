"""PortfolioAgent._parse_plan tablo testi.

Planlayıcının çıktısı doğrudan tool çağrısına dönüştüğü için buradaki her satır
bir güvenlik veya dayanıklılık kuralını temsil ediyor. Özellikle `user_id`
sızıntısı: modelin başka bir kullanıcının verisini istemesi mümkün olmamalı.
"""

import pytest

from agents.portfolio_agent import _MAX_TOOLS_PER_PLAN, _parse_plan

DURUMLAR = [
    (
        "temiz JSON",
        '[{"name": "get_portfolio_summary", "arguments": {}}]',
        [("get_portfolio_summary", {})],
    ),
    (
        "kod bloguna sarilmis",
        '```json\n[{"name": "get_holdings", "arguments": {}}]\n```',
        [("get_holdings", {})],
    ),
    (
        "duz metin icinde gomulu",
        'Tabii, plan su: [{"name": "get_holdings", "arguments": {}}] umarim yardimci olur.',
        [("get_holdings", {})],
    ),
    (
        "uydurma tool adi elenir",
        '[{"name": "get_crypto_prices", "arguments": {}}, {"name": "get_holdings", "arguments": {}}]',
        [("get_holdings", {})],
    ),
    (
        "sozluk olmayan argüman bos sozluge duser",
        '[{"name": "get_holdings", "arguments": "hepsi"}]',
        [("get_holdings", {})],
    ),
    (
        "ayni tool iki kez -> ilki",
        '[{"name": "get_holdings", "arguments": {}}, {"name": "get_holdings", "arguments": {"a": 1}}]',
        [("get_holdings", {})],
    ),
    ("bos dizi", "[]", []),
    ("hic JSON yok", "Bu soruya cevap veremem.", []),
    ("bozuk JSON", "[{name: get_holdings}]", []),
    ("dizi yerine sozluk", '{"name": "get_holdings"}', []),
]


@pytest.mark.parametrize("baslik,ham,beklenen", DURUMLAR, ids=[d[0] for d in DURUMLAR])
def test_parse_plan_table(baslik, ham, beklenen):
    assert _parse_plan(ham) == beklenen


def test_parse_plan_strips_user_id_written_by_the_model():
    """Guvenlik: user_id ajan tarafindan enjekte edilir, modelden gelmez."""
    ham = '[{"name": "get_holdings", "arguments": {"user_id": "baskasinin-uuid", "x": 1}}]'
    plan = _parse_plan(ham)
    assert plan == [("get_holdings", {"x": 1})]
    assert "user_id" not in plan[0][1]


def test_parse_plan_caps_tool_count():
    """Her tool ucretli token ve bir DB sorgusu; model hepsini isteyemez."""
    ham = (
        '[{"name": "get_portfolio_summary", "arguments": {}},'
        ' {"name": "get_holdings", "arguments": {}},'
        ' {"name": "get_portfolio_performance", "arguments": {}},'
        ' {"name": "get_transactions", "arguments": {}},'
        ' {"name": "get_benchmark_comparison", "arguments": {}}]'
    )
    assert len(_parse_plan(ham)) == _MAX_TOOLS_PER_PLAN
