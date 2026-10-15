import unittest
from datetime import datetime, timedelta, timezone

from strategy import Candle, NewsItem, StrategyEngine


class StrategyEngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
        self.news = [NewsItem(title="Regional escalation", source="Reuters")]
        self.query_windows: list[tuple[datetime, datetime]] = []

    async def matching_news(self, start: datetime, end: datetime):
        self.query_windows.append((start, end))
        return self.news

    def candle(
        self,
        interval: str,
        start: int,
        *,
        open_: float = 100.0,
        high: float = 100.5,
        low: float = 99.0,
        close: float = 100.0,
    ) -> Candle:
        return Candle(
            symbol="CLUSDT",
            interval=interval,
            start_ms=start,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=1.0,
        )

    def engine(self, news_query=None) -> StrategyEngine:
        return StrategyEngine(
            news_query=news_query or self.matching_news,
            now=lambda: self.now,
        )

    async def test_trigger_threshold_inclusive_and_queries_last_24_hours(self):
        engine = self.engine()
        await engine.on_1m(self.candle("1", 0, high=100.5))

        self.assertEqual(len(engine.candidates), 1)
        self.assertEqual(len(self.query_windows), 1)
        start, end = self.query_windows[0]
        self.assertEqual(end, self.now)
        self.assertEqual(start, self.now - timedelta(hours=24))

    async def test_below_trigger_threshold_does_not_query_news(self):
        engine = self.engine()
        await engine.on_1m(self.candle("1", 0, high=100.49))

        self.assertEqual(engine.candidates, [])
        self.assertEqual(self.query_windows, [])

    async def test_first_ratio_boundary_passes_and_second_close_emits_signal(self):
        engine = self.engine()
        await engine.on_1m(self.candle("1", 0))

        first = self.candle("5", 0, close=50.25)
        self.assertEqual(engine.on_5m(first), [])
        second = self.candle("5", 300_000, close=100.51)
        signals = engine.on_5m(second)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].first_ratio, 0.5)
        self.assertEqual(signals[0].first_5m, first)
        self.assertEqual(signals[0].second_5m, second)
        self.assertEqual(signals[0].news, tuple(self.news))
        self.assertEqual(engine.candidates, [])

    async def test_first_ratio_below_boundary_cancels_candidate(self):
        engine = self.engine()
        await engine.on_1m(self.candle("1", 0))

        engine.on_5m(self.candle("5", 0, close=50.24))

        self.assertEqual(engine.candidates, [])

    async def test_second_close_equal_to_trigger_high_does_not_signal(self):
        engine = self.engine()
        await engine.on_1m(self.candle("1", 0))
        engine.on_5m(self.candle("5", 0, close=50.25))

        signals = engine.on_5m(self.candle("5", 300_000, close=100.5))

        self.assertEqual(signals, [])
        self.assertEqual(engine.candidates, [])

    async def test_duplicate_candles_do_not_duplicate_candidate_or_signal(self):
        engine = self.engine()
        trigger = self.candle("1", 0)
        await engine.on_1m(trigger)
        await engine.on_1m(trigger)
        first = self.candle("5", 0, close=50.25)
        engine.on_5m(first)
        engine.on_5m(first)
        second = self.candle("5", 300_000, close=100.51)

        self.assertEqual(len(engine.on_5m(second)), 1)
        self.assertEqual(engine.on_5m(second), [])

    async def test_overlapping_candidates_are_tracked_independently(self):
        engine = self.engine()
        await engine.on_1m(self.candle("1", 0))
        engine.on_5m(self.candle("5", 0, close=50.25))
        await engine.on_1m(self.candle("1", 60_000))

        signals = engine.on_5m(self.candle("5", 300_000, close=100.51))

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].trigger.start_ms, 0)
        self.assertEqual(len(engine.candidates), 1)
        self.assertEqual(engine.candidates[0].trigger.start_ms, 60_000)

    async def test_missing_expected_5m_candle_cancels_candidate(self):
        engine = self.engine()
        await engine.on_1m(self.candle("1", 0))

        engine.on_5m(self.candle("5", 300_000, close=100.51))

        self.assertEqual(engine.candidates, [])

    async def test_empty_or_unavailable_news_stops_candidate(self):
        async def no_news(start: datetime, end: datetime):
            return []

        async def unavailable(start: datetime, end: datetime):
            return None

        no_news_engine = self.engine(no_news)
        unavailable_engine = self.engine(unavailable)
        await no_news_engine.on_1m(self.candle("1", 0))
        await unavailable_engine.on_1m(self.candle("1", 60_000))

        self.assertEqual(no_news_engine.candidates, [])
        self.assertEqual(unavailable_engine.candidates, [])


if __name__ == "__main__":
    unittest.main()