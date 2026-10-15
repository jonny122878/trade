import asyncio
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import websockets

from strategy import Candle, EntrySignal, StrategyEngine


BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"
SYMBOL = "CLUSDT"
LOG_PATH = Path(__file__).parent / "kline.log"
SUBSCRIPTION_TOPICS = [f"kline.1.{SYMBOL}", f"kline.5.{SYMBOL}"]
MAX_RECONNECT_DELAY_SECONDS = 60

logger = logging.getLogger("kline")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

prev_close_by_symbol: dict[str, float] = {}


def format_ts_tw(ms: int | None) -> str:
    if ms is None:
        return "-"
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc) + timedelta(hours=8)
    return dt.strftime("%Y-%m-%d %H:%M:%S +08:00")


def parse_candle(payload: dict[str, Any], interval: str, symbol: str) -> Candle:
    start_ms = int(payload["start"])
    prices = {
        "open": float(payload["open"]),
        "high": float(payload["high"]),
        "low": float(payload["low"]),
        "close": float(payload["close"]),
        "volume": float(payload.get("volume", 0)),
    }
    if not all(math.isfinite(value) for value in prices.values()):
        raise ValueError("candle contains a non-finite number")
    return Candle(
        symbol=str(payload.get("symbol") or symbol),
        interval=interval,
        start_ms=start_ms,
        **prices,
    )


def log_entry_signal(signal: EntrySignal) -> None:
    news_summary = "; ".join(
        f"{item.source}: {item.title}" for item in signal.news
    )
    logger.info(
        "[ENTRY SIGNAL] %s trigger_1m_time=%s trigger_1m_high=%s "
        "first_5m_time=%s first_5m_close=%s ratio=%.6f "
        "second_5m_time=%s second_5m_close=%s news=%s",
        signal.symbol,
        format_ts_tw(signal.trigger.start_ms),
        signal.trigger.high,
        format_ts_tw(signal.first_5m.start_ms),
        signal.first_5m.close,
        signal.first_ratio,
        format_ts_tw(signal.second_5m.start_ms),
        signal.second_5m.close,
        news_summary,
    )


async def handle_message(
    message: dict[str, Any],
    engine: StrategyEngine,
    previous_closes: dict[str, float] | None = None,
) -> list[EntrySignal]:
    topic = message.get("topic", "")
    topic_parts = topic.split(".")
    if len(topic_parts) != 3 or topic_parts[0] != "kline":
        return []
    interval, topic_symbol = topic_parts[1], topic_parts[2]
    if interval not in {"1", "5"}:
        return []

    data = message.get("data")
    if not isinstance(data, list):
        return []

    previous = previous_closes if previous_closes is not None else prev_close_by_symbol
    signals: list[EntrySignal] = []
    for payload in data:
        if not isinstance(payload, dict) or payload.get("confirm") is not True:
            continue
        try:
            candle = parse_candle(payload, interval, topic_symbol)
        except (KeyError, TypeError, ValueError) as error:
            logger.warning("Malformed %sm candle: %s", interval, error)
            continue
        if engine.has_seen(candle):
            continue

        if interval == "1":
            previous_close = previous.get(candle.symbol)
            pct_change = None
            if previous_close:
                pct_change = (candle.close - previous_close) / previous_close * 100
            logger.info(
                "CONFIRMED %s 1m start=%s open=%s high=%s low=%s close=%s "
                "vol=%s prev_close=%s pct_change=%s",
                candle.symbol,
                format_ts_tw(candle.start_ms),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                previous_close if previous_close is not None else "",
                f"{pct_change:.6f}%" if pct_change is not None else "",
            )
            previous[candle.symbol] = candle.close
            await engine.on_1m(candle)
        else:
            logger.info(
                "CONFIRMED %s 5m start=%s open=%s high=%s low=%s close=%s vol=%s",
                candle.symbol,
                format_ts_tw(candle.start_ms),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            )
            signals.extend(engine.on_5m(candle))

    for signal in signals:
        log_entry_signal(signal)
    return signals


async def run_forever(
    engine: StrategyEngine | None = None,
    connect: Any | None = None,
    sleep: Any = asyncio.sleep,
) -> None:
    strategy = engine or StrategyEngine(log=logger)
    connector = connect or websockets.connect
    reconnect_delay = 1

    while True:
        try:
            async with connector(
                BYBIT_WS_URL,
                ping_interval=20,
                ping_timeout=20,
            ) as websocket:
                await websocket.send(
                    json.dumps({"op": "subscribe", "args": SUBSCRIPTION_TOPICS})
                )
                logger.info("Subscribed to %s", ", ".join(SUBSCRIPTION_TOPICS))

                while True:
                    raw_message = await websocket.recv()
                    reconnect_delay = 1
                    try:
                        message = json.loads(raw_message)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning("Ignoring malformed WebSocket message")
                        continue
                    if isinstance(message, dict):
                        await handle_message(message, strategy)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning(
                "WebSocket disconnected: %s; reconnecting in %s seconds",
                error,
                reconnect_delay,
            )
            await sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, MAX_RECONNECT_DELAY_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_forever())