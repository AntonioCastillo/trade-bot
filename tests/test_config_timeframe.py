from tradebot.config import load_config

_YAML = """
mode: paper
timeframe: 1h
universe:
  - name: rapida
    symbols: [BTC/USDT]
    strategy: mean_reversion
    timeframe: 5m
  - name: lenta
    symbols: [ETH/USDT]
    strategy: mean_reversion
"""


def test_per_head_timeframe(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(_YAML, encoding="utf-8")
    c = load_config(str(p))
    # La cabeza rápida usa su propio timeframe; la otra hereda el global.
    assert c.instrument("BTC/USDT").timeframe == "5m"
    assert c.instrument("ETH/USDT").timeframe == "1h"
