import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from needle import (INTERVAL_MS, Candle, NeedleScanner, build_stream_url,
                    evaluate_window, load_symbols)


def make_payload(index, opening="100", closing="101", symbol="MAGICUSDT",
                 interval="15m", closed=True):
    return {
        "stream": f"{symbol.lower()}@kline_{interval}",
        "data": {
            "e": "kline",
            "s": symbol,
            "k": {
                "s": symbol,
                "i": interval,
                "x": closed,
                "t": index * INTERVAL_MS,
                "T": (index + 1) * INTERVAL_MS - 1,
                "o": opening,
                "c": closing,
            },
        },
    }


def make_candles(closes):
    return [
        Candle("MAGICUSDT", index * INTERVAL_MS, (index + 1) * INTERVAL_MS - 1,
               Decimal("100"), Decimal(close))
        for index, close in enumerate(closes)
    ]


class NeedleEvaluatorTests(unittest.TestCase):
    def test_five_green_bars_match(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = NeedleScanner(["MAGICUSDT"], Path(directory) / "needle.txt")
            results = [scanner.process_payload(make_payload(index)) for index in range(5)]
        self.assertTrue(all(result is None for result in results[:4]))
        self.assertEqual(results[-1]["green_count"], 5)
        self.assertEqual(results[-1]["red_count"], 0)
        self.assertEqual(results[-1]["evaluated_bar_open_time"], 4 * INTERVAL_MS)

    def test_four_green_and_one_red_match(self):
        signal = evaluate_window(make_candles(["101", "101", "99", "101", "101"]))
        self.assertEqual(signal["green_count"], 4)
        self.assertEqual(signal["red_count"], 1)

    def test_doji_counts_as_green(self):
        signal = evaluate_window(make_candles(["101", "100", "101", "101", "101"]))
        self.assertEqual(signal["green_count"], 5)
        self.assertEqual(signal["red_count"], 0)

    def test_three_green_and_two_red_do_not_match(self):
        self.assertIsNone(evaluate_window(make_candles(["101", "101", "101", "99", "99"])))

    def test_window_requires_five_contiguous_bars_of_one_symbol(self):
        candles = make_candles(["101"] * 5)
        self.assertIsNone(evaluate_window(candles[:4]))
        candles[-1] = Candle("BTCUSDT", candles[-1].open_time, candles[-1].close_time,
                             candles[-1].open, candles[-1].close)
        self.assertIsNone(evaluate_window(candles))
        candles[-1] = Candle("MAGICUSDT", 5 * INTERVAL_MS, 6 * INTERVAL_MS - 1,
                             candles[-1].open, candles[-1].close)
        self.assertIsNone(evaluate_window(candles))

    def test_open_duplicate_and_wrong_interval_events_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "needle.txt"
            scanner = NeedleScanner(["MAGICUSDT"], output)
            self.assertIsNone(scanner.process_payload(make_payload(0, closed=False)))
            self.assertIsNone(scanner.process_payload(make_payload(0, interval="5m")))
            for index in range(5):
                result = scanner.process_payload(make_payload(index))
            self.assertIsNotNone(result)
            self.assertIsNone(scanner.process_payload(make_payload(4)))
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 1)

    def test_gap_resets_symbol_warmup(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = NeedleScanner(["MAGICUSDT"], Path(directory) / "needle.txt")
            for index in range(4):
                self.assertIsNone(scanner.process_payload(make_payload(index)))
            self.assertIsNone(scanner.process_payload(make_payload(5)))
            for index in range(6, 10):
                signal = scanner.process_payload(make_payload(index))
            self.assertIsNotNone(signal)
            self.assertEqual(signal["candle_open_times"],
                             [5 * INTERVAL_MS, 6 * INTERVAL_MS, 7 * INTERVAL_MS,
                              8 * INTERVAL_MS, 9 * INTERVAL_MS])

    def test_symbols_have_isolated_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner = NeedleScanner(["MAGICUSDT", "BTCUSDT"], Path(directory) / "needle.txt")
            for index in range(5):
                scanner.process_payload(make_payload(index, symbol="MAGICUSDT"))
            self.assertEqual(len(scanner.windows["BTCUSDT"].candles), 0)

    def test_reconnect_preserves_contiguous_window(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "needle.txt"
            scanner = NeedleScanner(["MAGICUSDT"], output)
            scanner.stop_event.wait = lambda delay: False
            connection_attempt = 0

            class FakeConnection:
                def __init__(self, callbacks, indices, stop_after=False):
                    self.callbacks = callbacks
                    self.indices = indices
                    self.stop_after = stop_after

                def run_forever(self, **kwargs):
                    for index in self.indices:
                        self.callbacks["on_message"](
                            self, json.dumps(make_payload(index)))
                    if self.stop_after:
                        scanner.stop_event.set()

            def app_factory(url, **callbacks):
                nonlocal connection_attempt
                connection_attempt += 1
                indices = range(3) if connection_attempt == 1 else range(3, 5)
                return FakeConnection(callbacks, indices, stop_after=connection_attempt == 2)

            scanner.run(app_factory)
            record, = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(record["candle_open_times"], [i * INTERVAL_MS for i in range(5)])
            self.assertEqual(connection_attempt, 2)


class NeedleOutputAndConfigTests(unittest.TestCase):
    def test_output_file_is_created_empty_on_scanner_start(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data" / "needle.txt"
            NeedleScanner(["MAGICUSDT"], output)
            self.assertTrue(output.is_file())
            self.assertEqual(output.read_text(encoding="utf-8"), "")

    def test_matching_events_append_jsonl_record(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "needle.txt"
            scanner = NeedleScanner(["MAGICUSDT"], output)
            for index in range(5):
                scanner.process_payload(make_payload(index))
            record, = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(record["strategy_id"], "needle")
            self.assertEqual(record["symbol"], "MAGICUSDT")
            self.assertEqual(record["interval"], "15m")
            self.assertEqual(record["source"], "websocket")
            self.assertEqual(record["candle_open_times"], [i * INTERVAL_MS for i in range(5)])

    def test_closed_candles_append_to_symbol_file_with_color(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "needle.txt"
            scanner = NeedleScanner(["MAGICUSDT"], output)
            scanner.process_payload(make_payload(0, opening="100", closing="101"))
            scanner.process_payload(make_payload(1, opening="100", closing="99"))
            scanner.process_payload(make_payload(1, opening="100", closing="99"))

            candle_file = Path(directory) / "MAGICUSDT_15k.txt"
            records = [json.loads(line) for line in candle_file.read_text(
                encoding="utf-8").splitlines()]
            self.assertEqual([record["candle_color"] for record in records], ["綠K", "紅K"])
            self.assertEqual([record["open_time"] for record in records],
                             [0, INTERVAL_MS])
            self.assertEqual([record["symbol"] for record in records],
                             ["MAGICUSDT", "MAGICUSDT"])

    def test_config_symbols_are_validated_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "Contract.json"
            config.write_text(json.dumps({"monitor": {"symbols": [
                "MAGICUSDT", "BTCUSDT", "MAGICUSDT",
            ]}}), encoding="utf-8")
            self.assertEqual(load_symbols(config), ["MAGICUSDT", "BTCUSDT"])
            config.write_text(json.dumps({"monitor": {"symbols": ["MAGIC"]}}),
                              encoding="utf-8")
            with self.assertRaises(ValueError):
                load_symbols(config)

    def test_build_stream_url_uses_usdm_market_stream(self):
        self.assertEqual(
            build_stream_url(["MAGICUSDT", "BTCUSDT"]),
            "wss://fstream.binance.com/market/stream?streams="
            "magicusdt@kline_15m/btcusdt@kline_15m",
        )


if __name__ == "__main__":
    unittest.main()