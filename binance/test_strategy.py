import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from monitor import FeedError, Monitor
from strategy import Bar, INTERVAL_MS, SymbolState, evaluate


def make_bar(index, close="100", high="102", symbol="MAGICUSDT"):
    return Bar(symbol, index * INTERVAL_MS, (index + 1) * INTERVAL_MS - 1,
               "100", high, "90", close)


def signal_window(symbol="MAGICUSDT"):
    bars = [make_bar(index, high="102" if index % 2 == 0 else "103", symbol=symbol)
            for index in range(8)]
    bars.extend(make_bar(index, close=close, high="110", symbol=symbol)
                for index, close in enumerate(["101", "104", "102", "101"], 8))
    return bars


class StrategyTests(unittest.TestCase):
    def test_record_includes_taiwan_times_and_preserves_timestamps(self):
        bar = Bar("MAGICUSDT", 1791967500000, 1791968399999,
                  "0.114100", "0.114380", "0.113090", "0.113190")
        record = bar.record()
        self.assertEqual(record["open_time_tw"], "2026-10-14 16:45:00")
        self.assertEqual(record["close_time_tw"], "2026-10-14 16:59:59.999")
        self.assertEqual(record["open_time"], 1791967500000)
        self.assertEqual(record["close_time"], 1791968399999)
        self.assertEqual(Bar.from_record(record), bar)

    def test_old_records_without_readable_times_still_load(self):
        bar = make_bar(0)
        record = bar.record()
        del record["open_time_tw"]
        del record["close_time_tw"]
        self.assertEqual(Bar.from_record(record), bar)

    def test_signal_uses_disjoint_eight_plus_four(self):
        result = evaluate(signal_window())
        self.assertTrue(result["short_signal"])
        self.assertEqual(result["pressure_lower"], "102")
        self.assertEqual(result["pressure_upper"], "103")
        self.assertEqual(len(result["pressure_bar_open_times"]), 8)
        self.assertFalse(set(result["pressure_bar_open_times"]) &
                         set(result["signal_bar_open_times"]))

    def test_each_condition_can_reject_signal(self):
        for index, close in [(8, "102"), (9, "103"), (10, "101"), (11, "102")]:
            with self.subTest(index=index):
                bars = signal_window()
                bars[index] = make_bar(index, close=close, high="110")
                self.assertFalse(evaluate(bars)["short_signal"])

    def test_one_percent_inclusive(self):
        bars = signal_window()
        bars[:8] = [make_bar(0, "100"), make_bar(1, "101")] + [
            make_bar(index, str(200 + index * 10), str(201 + index * 10))
            for index in range(2, 8)]
        result = evaluate(bars)
        self.assertEqual(result["pressure_bar_open_times"], [0, INTERVAL_MS])
        bars[1] = make_bar(1, "101.000001")
        self.assertEqual(evaluate(bars)["reason"], "insufficient_pressure_candidates")

    def test_equal_size_groups_choose_most_recent(self):
        bars = signal_window()
        bars[:8] = [make_bar(index, str(100 + (index // 2) * 10),
                            str(102 + (index // 2) * 10)) for index in range(8)]
        self.assertEqual(evaluate(bars)["pressure_bar_open_times"],
                         [6 * INTERVAL_MS, 7 * INTERVAL_MS])

    def test_close_at_high_is_excluded(self):
        bars = signal_window()
        bars[:8] = [make_bar(index, "100", "100") for index in range(8)]
        self.assertEqual(evaluate(bars)["reason"], "insufficient_pressure_candidates")

    def test_gap_rejects_evaluation(self):
        bars = signal_window()
        bars[-1] = make_bar(12)
        self.assertEqual(evaluate(bars)["reason"], "non_contiguous_bars")

    def test_closed_only_deduplication_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            state = SymbolState("MAGICUSDT", Path(directory))
            for bar in signal_window():
                state.add(bar, "bootstrap", calculate=False)
            state.evaluate_latest("bootstrap")
            candle = {"s": "MAGICUSDT", "i": "15m", "x": False,
                      "t": 12 * INTERVAL_MS, "T": 13 * INTERVAL_MS - 1,
                      "o": "100", "h": "105", "l": "90", "c": "101"}
            payload = {"data": {"e": "kline", "k": candle}}
            self.assertFalse(state.handle_event(payload))
            candle["x"] = True
            self.assertTrue(state.handle_event(payload))
            self.assertFalse(state.handle_event(payload))
            restored = SymbolState("MAGICUSDT", Path(directory))
            self.assertFalse(restored.handle_event(payload))
            records = state.candle_path.read_text().splitlines()
            self.assertEqual(len(records), 13)
            self.assertTrue(all(json.loads(line)["candle"] is False for line in records))
            self.assertEqual(len(state.strategy_path.read_text().splitlines()), 2)

    def test_symbol_isolation_and_gap_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = SymbolState("MAGICUSDT", root)
            second = SymbolState("BTCUSDT", root)
            first.add(make_bar(0), "bootstrap")
            self.assertEqual(second.bars, [])
            with self.assertRaises(ValueError):
                second.add(make_bar(1), "websocket")
            with self.assertRaises(ValueError):
                first.add(make_bar(2), "websocket")


class FakeRest:
    def __init__(self, bars, boundary=12 * INTERVAL_MS):
        self.bars = bars
        self.current_boundary = boundary
        self.calls = []

    def boundary(self):
        return self.current_boundary

    def klines(self, symbol, end, start=None, limit=1000):
        self.calls.append((symbol, end, start, limit))
        bars = [bar for bar in self.bars if bar.symbol == symbol and
                bar.close_time < end and (start is None or bar.open_time >= start)]
        return bars[-limit:] if start is None else bars[:limit]


class MonitorTests(unittest.TestCase):
    def test_bootstrap_writes_twelve_bars_and_one_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            rest = FakeRest(signal_window() + [make_bar(12)])
            monitor = Monitor(["MAGICUSDT"], Path(directory), rest)
            monitor.synchronize_all()
            monitor.synchronize_all()
            state = monitor.states["MAGICUSDT"]
            self.assertEqual(len(state.candle_path.read_text().splitlines()), 12)
            self.assertEqual(len(state.strategy_path.read_text().splitlines()), 1)
            self.assertEqual(rest.calls[0], ("MAGICUSDT", 12 * INTERVAL_MS, None, 12))

    def test_websocket_gap_is_backfilled_before_new_bar(self):
        with tempfile.TemporaryDirectory() as directory:
            rest = FakeRest(signal_window() + [make_bar(12), make_bar(13)])
            monitor = Monitor(["MAGICUSDT"], Path(directory), rest)
            monitor.synchronize_all()
            candle = {"s": "MAGICUSDT", "i": "15m", "x": True,
                      "t": 14 * INTERVAL_MS, "T": 15 * INTERVAL_MS - 1,
                      "o": "100", "h": "105", "l": "90", "c": "101"}
            self.assertTrue(monitor.process({"e": "kline", "k": candle}))
            state = monitor.states["MAGICUSDT"]
            records = [json.loads(line) for line in state.candle_path.read_text().splitlines()]
            self.assertEqual([row["open_time"] for row in records],
                             list(range(0, 15 * INTERVAL_MS, INTERVAL_MS)))
            self.assertEqual([row["source"] for row in records[-3:]],
                             ["rest_backfill", "rest_backfill", "websocket"])
            self.assertEqual(len(state.strategy_path.read_text().splitlines()), 4)

    def test_missing_history_blocks_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = Monitor(["MAGICUSDT"], Path(directory), FakeRest(signal_window()[:-1]))
            with self.assertRaises(FeedError):
                monitor.synchronize_all()
            self.assertEqual(monitor.states["MAGICUSDT"].bars, [])

    def test_reconnect_and_multiple_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            rest = FakeRest(signal_window() + signal_window("BTCUSDT"))
            monitor = Monitor(["MAGICUSDT", "BTCUSDT"], Path(directory), rest)
            monitor.synchronize_all()
            rest.bars += [make_bar(12), make_bar(12, symbol="BTCUSDT")]
            rest.current_boundary = 13 * INTERVAL_MS
            restored = Monitor(["MAGICUSDT", "BTCUSDT"], Path(directory), rest)
            restored.synchronize_all()
            for symbol, state in restored.states.items():
                records = [json.loads(line) for line in state.candle_path.read_text().splitlines()]
                self.assertEqual(len(records), 13)
                self.assertTrue(all(row["symbol"] == symbol for row in records))
                self.assertEqual(len(state.strategy_path.read_text().splitlines()), 2)

    def test_crash_between_candle_and_strategy_is_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = SymbolState("MAGICUSDT", root)
            for bar in signal_window():
                state.add(bar, "bootstrap", calculate=False)
            SymbolState("MAGICUSDT", root)
            self.assertEqual(len(state.strategy_path.read_text().splitlines()), 1)
            SymbolState("MAGICUSDT", root)
            self.assertEqual(len(state.strategy_path.read_text().splitlines()), 1)

    def test_keyboard_interrupt_does_not_reconnect(self):
        class FakeConnection:
            def __init__(self, url, **callbacks):
                self.on_error = callbacks["on_error"]

            def run_forever(self, **options):
                self.on_error(self, KeyboardInterrupt())

            def close(self):
                pass

        fake_websocket = SimpleNamespace(WebSocketApp=FakeConnection,
                                         setdefaulttimeout=lambda timeout: None)
        with tempfile.TemporaryDirectory() as directory:
            monitor = Monitor(["MAGICUSDT"], Path(directory), FakeRest(signal_window()))
            with patch.dict("sys.modules", {"websocket": fake_websocket}):
                with self.assertRaises(KeyboardInterrupt):
                    monitor.run()


if __name__ == "__main__":
    unittest.main()