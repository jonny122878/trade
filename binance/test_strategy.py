import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from monitor import FeedError, Monitor, parse_arguments
from strategy import (Bar, INTERVAL_MS, INTERVAL_MS_BY_INTERVAL, RepeatSignals,
                      SymbolState, append_record, evaluate)
from spotgoods_strategy import SpotGoodsState, evaluate as evaluate_spotgoods


def make_bar(index, close="100", high="102", symbol="MAGICUSDT", interval="15m"):
    interval_ms = INTERVAL_MS_BY_INTERVAL[interval]
    return Bar(symbol, index * interval_ms, (index + 1) * interval_ms - 1,
               "100", high, "90", close, interval)


def signal_window(symbol="MAGICUSDT", interval="15m"):
    bars = [make_bar(index, high="102" if index % 2 == 0 else "103",
                     symbol=symbol, interval=interval)
            for index in range(8)]
    signal_bars = [("101", "102"), ("102.8", "104"),
                   ("102.3", "103"), ("101", "102")]
    bars.extend(make_bar(index, close=close, high=high, symbol=symbol, interval=interval)
                for index, (close, high) in enumerate(signal_bars, 8))
    return bars


def make_spot_bar(index, high="101.01", close="100.1", symbol="MAGICUSDT"):
    return Bar(symbol, index * 60_000, (index + 1) * 60_000 - 1,
               "100", high, "99", close, "1m")


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
        self.assertEqual(result["rules_version"], 2)
        self.assertEqual(result["pressure_lower"], "102")
        self.assertEqual(result["pressure_upper"], "103")
        self.assertEqual(len(result["pressure_bar_open_times"]), 8)
        self.assertFalse(set(result["pressure_bar_open_times"]) &
                         set(result["signal_bar_open_times"]))

    def test_second_bar_must_wick_above_zone_and_close_inside(self):
        bars = signal_window()
        result = evaluate(bars)
        self.assertTrue(result["conditions"]["second_wick_breaks_upper"])
        self.assertTrue(result["conditions"]["second_inside_zone"])

        bars[9] = make_bar(9, close="102.8", high="103")
        result = evaluate(bars)
        self.assertFalse(result["conditions"]["second_wick_breaks_upper"])
        self.assertFalse(result["short_signal"])

    def test_evaluation_supports_all_requested_intervals(self):
        for interval in ("5m", "15m", "1h", "4h"):
            with self.subTest(interval=interval):
                result = evaluate(signal_window(interval=interval))
                self.assertTrue(result["short_signal"])
                self.assertEqual(result["interval"], interval)

    def test_signals_from_all_intervals_share_signal_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for interval in ("5m", "15m", "1h", "4h"):
                state = SymbolState("MAGICUSDT", root, interval)
                for bar in signal_window(interval=interval):
                    state.add(bar, "bootstrap", calculate=False)
                state.evaluate_latest("bootstrap")
            records = [json.loads(line) for line in (root / "signals.txt").read_text().splitlines()]
            self.assertEqual([record["interval"] for record in records],
                             ["5m", "15m", "1h", "4h"])

    def test_each_condition_can_reject_signal(self):
        invalid_closes = [
            {8: "102"},
            {9: "103.000001"},
            {10: "101.999999"},
            {9: "102.3", 10: "102.8"},
            {11: "102"},
        ]
        for replacements in invalid_closes:
            with self.subTest(replacements=replacements):
                bars = signal_window()
                for index, close in replacements.items():
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
            signal_records = state.signal_path.read_text().splitlines()
            self.assertEqual(len(signal_records), 1)
            signal_record = json.loads(signal_records[0])
            self.assertEqual(signal_record["symbol"], "MAGICUSDT")
            self.assertTrue(signal_record["short_signal"])
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
            self.assertEqual(len(state.signal_path.read_text().splitlines()), 1)

    def test_non_signal_is_not_written_to_shared_signal_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = SymbolState("MAGICUSDT", root)
            bars = signal_window()
            bars[9] = make_bar(9, close="103.000001", high="110")
            for bar in bars:
                state.add(bar, "bootstrap", calculate=False)
            state.evaluate_latest("bootstrap")
            self.assertFalse(state.signal_path.exists())

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


class SpotGoodsStrategyTests(unittest.TestCase):
    def test_three_consecutive_green_bars_require_strictly_more_than_one_percent(self):
        bars = [make_spot_bar(index) for index in range(3)]
        self.assertTrue(evaluate_spotgoods(bars)["long_signal"])

        bars[1] = make_spot_bar(1, high="101")
        result = evaluate_spotgoods(bars)
        self.assertFalse(result["long_signal"])
        self.assertFalse(result["conditions"][1]["high_gain_over_threshold"])

        bars[1] = make_spot_bar(1, close="100")
        result = evaluate_spotgoods(bars)
        self.assertFalse(result["long_signal"])
        self.assertFalse(result["conditions"][1]["green_candle"])

    def test_non_contiguous_or_mixed_symbol_bars_do_not_signal(self):
        bars = [make_spot_bar(index) for index in range(3)]
        bars[2] = make_spot_bar(3)
        self.assertEqual(evaluate_spotgoods(bars)["reason"], "non_contiguous_bars")

        bars = [make_spot_bar(0), make_spot_bar(1), make_spot_bar(2, symbol="BTCUSDT")]
        self.assertEqual(evaluate_spotgoods(bars)["reason"], "mixed_symbol_or_interval")

    def test_state_appends_one_labeled_signal_per_qualifying_streak(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = SpotGoodsState("MAGICUSDT", root)
            for index in range(4):
                state.add(make_spot_bar(index), "websocket")
            signals = [json.loads(line) for line in (root / "signals.txt").read_text().splitlines()]
            self.assertEqual(len(signals), 1)
            self.assertEqual(signals[0]["strategy_id"], "spotgoods")
            self.assertEqual(signals[0]["market"], "spot")
            self.assertEqual(signals[0]["direction"], "long")
            self.assertEqual(signals[0]["source"], "websocket")

            restored = SpotGoodsState("MAGICUSDT", root)
            restored.add(make_spot_bar(4), "websocket")
            self.assertEqual(len((root / "signals.txt").read_text().splitlines()), 1)


class RepeatSignalsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.now = 100 * INTERVAL_MS_BY_INTERVAL["4h"] + 37 * 60_000
        self.keys = {("MAGICUSDT", interval) for interval in INTERVAL_MS_BY_INTERVAL}
        self.repeats = RepeatSignals(self.root, self.keys, clock=lambda: self.now)

    def record(self, interval, source="websocket", short_signal=True):
        interval_ms = INTERVAL_MS_BY_INTERVAL[interval]
        return {
            "symbol": "MAGICUSDT", "interval": interval,
            "evaluated_bar_open_time": self.now // interval_ms * interval_ms - interval_ms,
            "short_signal": short_signal, "source": source,
        }

    def summaries(self):
        return [json.loads(line) for line in self.repeats.path.read_text().splitlines()]

    def test_all_four_latest_closed_intervals_are_counted_once(self):
        for interval in INTERVAL_MS_BY_INTERVAL:
            self.repeats.update(self.record(interval))
            self.repeats.update(self.record(interval))
        summary, = self.summaries()
        self.assertEqual(summary["intervals"], ["5m", "15m", "1h", "4h"])
        self.assertEqual(summary["total_count"], 4)
        self.assertEqual(summary["distinct_interval_count"], 4)
        self.assertEqual(summary["generated_at"], self.now)
        for signal in summary["signals"]:
            interval_ms = INTERVAL_MS_BY_INTERVAL[signal["interval"]]
            self.assertEqual(signal["confirmed_at"], self.now // interval_ms * interval_ms)
            self.assertEqual(signal["expires_at"], signal["confirmed_at"] + interval_ms)
            self.assertIn("evaluated_bar_open_time_tw", signal)

    def test_single_interval_and_old_or_future_bars_do_not_repeat(self):
        self.repeats.update(self.record("5m"))
        for offset in (-1, 1):
            record = self.record("15m")
            record["evaluated_bar_open_time"] += offset * INTERVAL_MS
            self.repeats.update(record)
            self.assertEqual(self.summaries(), [])

    def test_refresh_expires_at_each_interval_boundary_without_events(self):
        for interval in INTERVAL_MS_BY_INTERVAL:
            self.repeats.update(self.record(interval))
        for elapsed_minutes, expected in (
            (40, ["15m", "1h", "4h"]),
            (45, ["1h", "4h"]),
            (60, []),
        ):
            self.now = 100 * INTERVAL_MS_BY_INTERVAL["4h"] + elapsed_minutes * 60_000
            self.repeats.refresh()
            summaries = self.summaries()
            self.assertEqual(summaries[0]["intervals"] if summaries else [], expected)

    def test_non_signal_removes_interval_and_old_update_cannot_restore_it(self):
        self.repeats.update(self.record("5m"))
        old = self.record("15m")
        self.repeats.update(old)
        self.assertEqual(len(self.summaries()), 1)
        self.now += INTERVAL_MS
        self.repeats.update(self.record("5m"))
        self.repeats.update(self.record("15m", short_signal=False))
        self.repeats.update(old)
        self.assertEqual(self.summaries(), [])

    def test_historical_sources_do_not_count_as_live_confirmation(self):
        self.repeats.update(self.record("5m"))
        for source in ("bootstrap", "rest_backfill", "recovery"):
            self.repeats.update(self.record("15m", source=source))
            self.assertEqual(self.summaries(), [])

    def test_repeat_snapshot_retries_temporary_replace_permission_error(self):
        original_replace = Path.replace
        attempts = 0

        def fail_twice_then_replace(source, target):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise PermissionError("temporarily denied")
            return original_replace(source, target)

        with patch.object(Path, "replace", new=fail_twice_then_replace):
            with patch("strategy.time.sleep") as sleep:
                self.repeats.refresh()

        self.assertEqual(attempts, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_repeat_snapshot_stops_after_five_replace_permission_errors(self):
        attempts = 0

        def always_fail_replace(source, target):
            nonlocal attempts
            attempts += 1
            raise PermissionError("still denied")

        with patch.object(Path, "replace", new=always_fail_replace):
            with patch("strategy.time.sleep") as sleep:
                with self.assertRaisesRegex(PermissionError, "still denied"):
                    self.repeats.refresh()

        self.assertEqual(attempts, 5)
        self.assertEqual(sleep.call_count, 4)

    def test_restart_loads_legacy_records_but_filters_unmonitored_keys(self):
        for interval in ("5m", "15m", "1h"):
            record = self.record(interval)
            if interval == "15m":
                del record["interval"]
            append_record(self.root / "signals.txt", record)
        self.repeats = RepeatSignals(self.root, self.keys - {("MAGICUSDT", "1h")},
                                     clock=lambda: self.now)
        summary, = self.summaries()
        self.assertEqual(summary["intervals"], ["5m", "15m"])
        self.assertEqual(len((self.root / "signals.txt").read_text().splitlines()), 3)

    def test_parallel_updates_produce_complete_json_without_lost_intervals(self):
        records = [self.record(interval) for interval in INTERVAL_MS_BY_INTERVAL] * 5
        with ThreadPoolExecutor(max_workers=4) as workers:
            list(workers.map(self.repeats.update, records))
        summary, = self.summaries()
        self.assertEqual(summary["total_count"], 4)
        self.assertFalse(self.repeats.path.with_suffix(".tmp").exists())


class FakeRest:
    def __init__(self, bars, boundary=12 * INTERVAL_MS):
        self.bars = bars
        self.current_boundary = boundary
        self.calls = []

    def boundary(self, interval="15m"):
        return self.current_boundary

    def klines(self, symbol, end, start=None, limit=1000, interval="15m"):
        self.calls.append((symbol, end, start, limit, interval))
        bars = [bar for bar in self.bars if bar.symbol == symbol and
                bar.interval == interval and
                bar.close_time < end and (start is None or bar.open_time >= start)]
        return bars[-limit:] if start is None else bars[:limit]


class FakeSpotRest:
    def __init__(self, bars, boundary):
        self.bars = bars
        self.current_boundary = boundary

    def available_symbols(self):
        return {"MAGICUSDT"}

    def boundary(self):
        return self.current_boundary

    def klines(self, symbol, end, start=None, limit=1000):
        bars = [bar for bar in self.bars if bar.symbol == symbol and
                bar.close_time < end and (start is None or bar.open_time >= start)]
        return bars[-limit:] if start is None else bars[:limit]


class MonitorTests(unittest.TestCase):
    def test_spotgoods_config_defaults_to_monitor_symbols_without_network(self):
        with patch("sys.argv", ["monitor.py", "--symbols", "BTCUSDT"]):
            arguments = parse_arguments()
        self.assertEqual(arguments.spotgoods_symbols, ("BTCUSDT",))
        self.assertEqual(arguments.intervals, ("5m", "15m", "1h", "4h"))

    def test_spotgoods_uses_spot_closed_one_minute_candles_and_shared_signals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial_bars = [make_spot_bar(index, high="100.5") for index in range(3)]
            spot_rest = FakeSpotRest(initial_bars, boundary=3 * 60_000)
            monitor = Monitor(
                ["MAGICUSDT"], root, FakeRest([]),
                spotgoods_symbols=["MAGICUSDT", "NO_SPOTUSDT"],
                spot_rest=spot_rest,
            )
            monitor.synchronize_spotgoods_all()
            self.assertEqual(set(monitor.spotgoods_states), {"MAGICUSDT"})

            def payload(index, closed=True):
                return {"e": "kline", "k": {
                    "s": "MAGICUSDT", "i": "1m", "x": closed,
                    "t": index * 60_000, "T": (index + 1) * 60_000 - 1,
                    "o": "100", "h": "101.01", "l": "99", "c": "100.1",
                }}

            self.assertFalse(monitor.process_spotgoods(payload(3, closed=False)))
            for index in (3, 4, 5):
                self.assertTrue(monitor.process_spotgoods(payload(index)))

            signals = [json.loads(line) for line in (root / "signals.txt").read_text().splitlines()]
            self.assertEqual(len(signals), 1)
            self.assertEqual(signals[0]["strategy_id"], "spotgoods")
            self.assertEqual(signals[0]["source"], "websocket")
            self.assertEqual(signals[0]["interval"], "1m")

    def test_live_signals_share_snapshot_and_restart_without_duplicate_history(self):
        intervals = tuple(INTERVAL_MS_BY_INTERVAL)
        now = 100 * INTERVAL_MS_BY_INTERVAL["4h"] + 37 * 60_000
        with tempfile.TemporaryDirectory() as directory, patch("strategy.time.time_ns",
                                                              return_value=now * 1_000_000):
            root = Path(directory)
            monitor = Monitor(["MAGICUSDT"], root, FakeRest([]), intervals=intervals)
            for interval in intervals:
                state = monitor.states[("MAGICUSDT", interval)]
                self.assertIs(state.repeat_signals, monitor.repeat_signals)
                interval_ms = INTERVAL_MS_BY_INTERVAL[interval]
                offset = now // interval_ms - 12
                bars = [make_bar(index + offset, close=bar.close, high=bar.high, interval=interval)
                        for index, bar in enumerate(signal_window(interval=interval))]
                for bar in bars[:-1]:
                    state.add(bar, "bootstrap", calculate=False)
                state.add(bars[-1], "websocket")
            summary = json.loads(monitor.repeat_signals.path.read_text())
            self.assertEqual(summary["intervals"], list(intervals))
            history = (root / "signals.txt").read_bytes()
            restored = Monitor(["MAGICUSDT"], root, FakeRest([]), intervals=intervals)
            self.assertEqual(json.loads(restored.repeat_signals.path.read_text())["total_count"], 4)
            self.assertEqual((root / "signals.txt").read_bytes(), history)
            with patch("strategy.time.time_ns", return_value=(now + 3 * 60_000) * 1_000_000):
                restored.repeat_signals.refresh()
            self.assertEqual(json.loads(restored.repeat_signals.path.read_text())["intervals"],
                             ["15m", "1h", "4h"])

    def test_refresh_worker_runs_without_candle_events(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = Monitor(["MAGICUSDT"], Path(directory), FakeRest([]))
            with patch.object(monitor.stop_event, "wait", side_effect=[False, True]), \
                    patch.object(monitor.repeat_signals, "refresh") as refresh:
                monitor._refresh_repeat_signals()
            refresh.assert_called_once_with()

    def test_refresh_failure_stops_monitor(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = Monitor(["MAGICUSDT"], Path(directory), FakeRest([]))
            failure = OSError("snapshot unavailable")
            with patch.object(monitor.stop_event, "wait", return_value=False), \
                    patch.object(monitor.repeat_signals, "refresh", side_effect=failure), \
                    self.assertLogs("binance.monitor", level="ERROR"):
                monitor._refresh_repeat_signals()
            self.assertIs(monitor.failure, failure)
            self.assertTrue(monitor.stop_event.is_set())

    def test_one_hour_bootstrap_uses_hourly_rest_data_and_state(self):
        interval = "1h"
        interval_ms = INTERVAL_MS_BY_INTERVAL[interval]
        with tempfile.TemporaryDirectory() as directory:
            rest = FakeRest(signal_window(interval=interval), boundary=12 * interval_ms)
            monitor = Monitor(["MAGICUSDT"], Path(directory), rest, intervals=(interval,))
            monitor.synchronize_all()
            state = monitor.states[("MAGICUSDT", interval)]
            self.assertEqual(state.interval, interval)
            self.assertEqual(len(state.bars), 12)
            self.assertEqual(rest.calls[0], ("MAGICUSDT", 12 * interval_ms, None, 12, interval))
            record = json.loads(state.strategy_path.read_text().splitlines()[0])
            self.assertEqual(record["interval"], interval)

    def test_monitor_creates_independent_states_per_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            intervals = ("5m", "15m", "1h", "4h")
            monitor = Monitor(["MAGICUSDT"], Path(directory), FakeRest([]), intervals=intervals)
            self.assertEqual(set(monitor.states), {("MAGICUSDT", interval) for interval in intervals})
            self.assertEqual(len({state.candle_path for state in monitor.states.values()}), 4)

    def test_websocket_routes_closed_candle_by_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            intervals = ("5m", "1h")
            monitor = Monitor(["MAGICUSDT"], Path(directory), FakeRest([]), intervals=intervals)
            for interval in intervals:
                state = monitor.states[("MAGICUSDT", interval)]
                for bar in signal_window(interval=interval):
                    state.add(bar, "bootstrap", calculate=False)
            interval_ms = INTERVAL_MS_BY_INTERVAL["5m"]
            candle = {
                "s": "MAGICUSDT", "i": "5m", "x": True,
                "t": 12 * interval_ms, "T": 13 * interval_ms - 1,
                "o": "100", "h": "105", "l": "90", "c": "101",
            }
            self.assertTrue(monitor.process({"e": "kline", "k": candle}))
            self.assertEqual(monitor.states[("MAGICUSDT", "5m")].last_open_time,
                             12 * interval_ms)
            self.assertEqual(monitor.states[("MAGICUSDT", "1h")].last_open_time,
                             11 * INTERVAL_MS_BY_INTERVAL["1h"])

    def test_bootstrap_writes_twelve_bars_and_one_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            rest = FakeRest(signal_window() + [make_bar(12)])
            monitor = Monitor(["MAGICUSDT"], Path(directory), rest)
            monitor.synchronize_all()
            monitor.synchronize_all()
            state = monitor.states[("MAGICUSDT", "15m")]
            self.assertEqual(len(state.candle_path.read_text().splitlines()), 12)
            self.assertEqual(len(state.strategy_path.read_text().splitlines()), 1)
            self.assertEqual(rest.calls[0], ("MAGICUSDT", 12 * INTERVAL_MS, None, 12, "15m"))

    def test_websocket_gap_is_backfilled_before_new_bar(self):
        with tempfile.TemporaryDirectory() as directory:
            rest = FakeRest(signal_window() + [make_bar(12), make_bar(13)])
            monitor = Monitor(["MAGICUSDT"], Path(directory), rest)
            monitor.synchronize_all()
            candle = {"s": "MAGICUSDT", "i": "15m", "x": True,
                      "t": 14 * INTERVAL_MS, "T": 15 * INTERVAL_MS - 1,
                      "o": "100", "h": "105", "l": "90", "c": "101"}
            self.assertTrue(monitor.process({"e": "kline", "k": candle}))
            state = monitor.states[("MAGICUSDT", "15m")]
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
            self.assertEqual(monitor.states[("MAGICUSDT", "15m")].bars, [])

    def test_reconnect_and_multiple_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            rest = FakeRest(signal_window() + signal_window("BTCUSDT"))
            monitor = Monitor(["MAGICUSDT", "BTCUSDT"], Path(directory), rest)
            monitor.synchronize_all()
            rest.bars += [make_bar(12), make_bar(12, symbol="BTCUSDT")]
            rest.current_boundary = 13 * INTERVAL_MS
            restored = Monitor(["MAGICUSDT", "BTCUSDT"], Path(directory), rest)
            restored.synchronize_all()
            for (symbol, interval), state in restored.states.items():
                records = [json.loads(line) for line in state.candle_path.read_text().splitlines()]
                self.assertEqual(len(records), 13)
                self.assertTrue(all(row["symbol"] == symbol for row in records))
                self.assertTrue(all(row["interval"] == interval for row in records))
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