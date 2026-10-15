import asyncio
import json
import unittest
from datetime import datetime, timezone

from strategy import Candle, NewsItem, StrategyEngine
from test import SUBSCRIPTION_TOPICS, handle_message, run_forever


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        raise asyncio.CancelledError


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket, fail: bool = False) -> None:
        self.websocket = websocket
        self.fail = fail

    async def __aenter__(self):
        if self.fail:
            raise OSError("test connection failure")
        return self.websocket

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        return None


class FakeConnector:
    def __init__(self, failures: int = 1) -> None:
        self.websocket = FakeWebSocket()
        self.calls = 0
        self.failures = failures

    def __call__(self, *_args, **_kwargs) -> FakeConnection:
        self.calls += 1
        return FakeConnection(self.websocket, fail=self.calls <= self.failures)


class WebSocketClientTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def bybit_payload(candle: Candle) -> dict[str, str | bool]:
        return {
            "symbol": candle.symbol,
            "start": str(candle.start_ms),
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": str(candle.volume),
            "confirm": True,
        }

    async def test_subscribes_to_both_intervals_after_reconnect(self):
        connector = FakeConnector(failures=2)
        delays: list[int] = []

        async def fake_sleep(delay: int) -> None:
            delays.append(delay)

        with self.assertRaises(asyncio.CancelledError):
            await run_forever(connect=connector, sleep=fake_sleep)

        self.assertEqual(connector.calls, 3)
        self.assertEqual(delays, [1, 2])
        self.assertEqual(
            json.loads(connector.websocket.sent[0]),
            {"op": "subscribe", "args": SUBSCRIPTION_TOPICS},
        )

    async def test_message_handler_ignores_unconfirmed_and_routes_both_intervals(self):
        now = datetime(2026, 10, 2, tzinfo=timezone.utc)

        async def news_query(_start, _end):
            return [NewsItem(title="Confirmed report", source="AP")]

        engine = StrategyEngine(news_query=news_query, now=lambda: now)
        previous_closes: dict[str, float] = {}
        one_minute = {
            "topic": "kline.1.CLUSDT",
            "data": [
                {
                    "symbol": "CLUSDT",
                    "start": "0",
                    "open": "100",
                    "high": "101",
                    "low": "99",
                    "close": "100.5",
                    "volume": "4",
                    "confirm": False,
                },
                {
                    "symbol": "CLUSDT",
                    "start": "60000",
                    "open": "100",
                    "high": "100.5",
                    "low": "99",
                    "close": "100.2",
                    "volume": "5",
                    "confirm": True,
                },
            ],
        }
        await handle_message(one_minute, engine, previous_closes)
        self.assertEqual(len(engine.candidates), 1)
        self.assertEqual(previous_closes["CLUSDT"], 100.2)
        duplicate = Candle("CLUSDT", "1", 60_000, 100, 101, 99, 111, 5)
        await handle_message(
            {
                "topic": "kline.1.CLUSDT",
                "data": [self.bybit_payload(duplicate)],
            },
            engine,
            previous_closes,
        )
        self.assertEqual(previous_closes["CLUSDT"], 100.2)
        self.assertEqual(len(engine.candidates), 1)

        first_5m = Candle("CLUSDT", "5", 0, 100, 101, 49, 50.25, 10)
        second_5m = Candle("CLUSDT", "5", 300_000, 100, 102, 99, 100.6, 12)
        await handle_message(
            {
                "topic": "kline.5.CLUSDT",
                "data": [self.bybit_payload(first_5m)],
            },
            engine,
            previous_closes,
        )
        signals = await handle_message(
            {
                "topic": "kline.5.CLUSDT",
                "data": [self.bybit_payload(second_5m)],
            },
            engine,
            previous_closes,
        )

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].trigger.start_ms, 60_000)


if __name__ == "__main__":
    unittest.main()