"""Runner del funding-rate carry (delta-neutral) en modo PAPER, standalone.

Usa datos REALES (funding + precio spot + precio perp) pero NO ejecuta órdenes
reales. Normalmente el carry ya corre dentro del bot (como una cabeza más); este
script es para lanzarlo suelto o hacer una pasada de prueba.

Uso:
    python scripts/carry.py          # bucle continuo (paper)
    python scripts/carry.py once     # una sola pasada (para probar)
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tradebot.carry import CarryRunner  # noqa: E402
from tradebot.config import load_config  # noqa: E402
from tradebot.exchange import Exchange  # noqa: E402
from tradebot.factory import setup_logging  # noqa: E402
from tradebot.notifier import PrefixNotifier, build_notifier  # noqa: E402


def main() -> None:
    once = len(sys.argv) > 1 and sys.argv[1] == "once"
    config = load_config()
    setup_logging(config.log_level)
    # Etiqueta según el modo efectivo (paper, o futuros real/dry-run).
    live_futures = config.mode == "live" and config.credentials.is_complete
    tag = "🔴 [CARRY FUTUROS]" if live_futures else "🧪 [CARRY PAPER]"
    notifier = PrefixNotifier(
        build_notifier(config.credentials.telegram_token, config.credentials.telegram_chat_id),
        tag,
    )
    runner = CarryRunner(config, Exchange(config), notifier)
    if once:
        runner.cycle()
    else:
        runner.run_forever()


if __name__ == "__main__":
    main()
