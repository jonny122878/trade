import argparse
import json
import logging
import random
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from strategy import Bar, INTERVAL_MS_BY_INTERVAL, RepeatSignals, SUPPORTED_INTERVALS, SymbolState
from spotgoods_strategy import INTERVAL as SPOTGOODS_INTERVAL
from spotgoods_strategy import INTERVAL_MS as SPOTGOODS_INTERVAL_MS
from spotgoods_strategy import SpotGoodsState


LOGGER = logging.getLogger("binance.monitor")
REST_URL = "https://fapi.binance.com"
STREAM_URL = "wss://fstream.binance.com/market/stream?streams="
SPOT_REST_URL = "https://api.binance.com"
SPOT_STREAM_URL = "wss://stream.binance.com:9443/stream?streams="


class FeedError(RuntimeError):
    pass


class FuturesRest:
    def __init__(self, base_url: str = REST_URL):
        self.base_url = base_url

    def request(self, route: str, **parameters):
        url = self.base_url + route
        if parameters:
            url += "?" + urlencode(parameters)
        for attempt in range(5):
            delay = min(2 ** attempt, 30)
            try:
                request = Request(url, headers={"User-Agent": "binance-multi-interval-monitor/1"})
                with urlopen(request, timeout=20) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code not in (418, 429) and error.code < 500:
                    raise FeedError(f"Binance rejected {url}: {error.read().decode()}") from error
                delay = max(delay, float(error.headers.get("Retry-After", delay)))
            except (URLError, TimeoutError, OSError) as error:
                LOGGER.warning("REST request failed: %s", error)
            if attempt < 4:
                time.sleep(delay)
        raise FeedError(f"REST retries exhausted: {url}")

    def boundary(self, interval: str = "15m") -> int:
        server_time = int(self.request("/fapi/v1/time")["serverTime"])
        interval_ms = INTERVAL_MS_BY_INTERVAL[interval]
        return server_time // interval_ms * interval_ms

    def klines(self, symbol: str, end: int, start=None, limit: int = 1000,
               interval: str = "15m") -> list[Bar]:
        parameters = {"symbol": symbol, "interval": interval, "endTime": end - 1, "limit": limit}
        if start is not None:
            parameters["startTime"] = start
        rows = self.request("/fapi/v1/klines", **parameters)
        return [Bar.from_rest(symbol, row, interval) for row in rows
                if int(row[6]) < end and (start is None or int(row[0]) >= start)]


class SpotRest(FuturesRest):
    def __init__(self):
        super().__init__(SPOT_REST_URL)

    def boundary(self) -> int:
        server_time = int(self.request("/api/v3/time")["serverTime"])
        return server_time // SPOTGOODS_INTERVAL_MS * SPOTGOODS_INTERVAL_MS

    def klines(self, symbol: str, end: int, start=None, limit: int = 1000) -> list[Bar]:
        parameters = {
            "symbol": symbol,
            "interval": SPOTGOODS_INTERVAL,
            "endTime": end - 1,
            "limit": limit,
        }
        if start is not None:
            parameters["startTime"] = start
        rows = self.request("/api/v3/klines", **parameters)
        return [Bar.from_rest(symbol, row, SPOTGOODS_INTERVAL) for row in rows
                if int(row[6]) < end and (start is None or int(row[0]) >= start)]

    def available_symbols(self) -> set[str]:
        exchange_info = self.request("/api/v3/exchangeInfo")
        return {
            item["symbol"] for item in exchange_info["symbols"]
            if item.get("status") == "TRADING"
            and item.get("quoteAsset") == "USDT"
            and item.get("isSpotTradingAllowed") is True
        }


class Monitor:
    def __init__(self, symbols: list[str], output: Path, rest=None,
                 intervals: tuple[str, ...] = ("15m",), spotgoods_symbols=None,
                 spot_rest=None):
        if not intervals or any(interval not in INTERVAL_MS_BY_INTERVAL for interval in intervals):
            raise ValueError(f"Intervals must be selected from {SUPPORTED_INTERVALS}")
        self.rest = rest if rest is not None else FuturesRest()
        self.output = output
        self.intervals = tuple(dict.fromkeys(intervals))
        keys = {(symbol, interval) for symbol in symbols for interval in self.intervals}
        self.repeat_signals = RepeatSignals(output, keys)
        self.states = {
            (symbol, interval): SymbolState(symbol, output, interval, self.repeat_signals)
            for symbol in symbols for interval in self.intervals
        }
        self.spotgoods_symbols = tuple(dict.fromkeys(spotgoods_symbols or ()))
        self.spot_rest = spot_rest if spot_rest is not None else (
            SpotRest() if self.spotgoods_symbols else None
        )
        self.spotgoods_states: dict[str, SpotGoodsState] = {}
        self.failure = None
        self.stop_event = threading.Event()
        self.connections = {}
        self.connections_lock = threading.Lock()

    def synchronize(self, state: SymbolState, boundary: int) -> None:
        if state.last_open_time is None:
            bars = self.rest.klines(state.symbol, boundary, limit=12, interval=state.interval)
            expected = list(range(
                boundary - 12 * state.interval_ms, boundary, state.interval_ms,
            ))
            if [bar.open_time for bar in bars] != expected:
                raise FeedError(
                    f"Expected 12 consecutive completed {state.interval} bars for {state.symbol}"
                )
            for bar in bars:
                state.add(bar, "bootstrap", calculate=False)
            state.evaluate_latest("bootstrap")
            LOGGER.info("%s %s initialized with 12 closed candles", state.symbol, state.interval)
            return
        cursor = state.last_open_time + state.interval_ms
        while cursor < boundary:
            bars = self.rest.klines(state.symbol, boundary, start=cursor, interval=state.interval)
            if not bars or bars[0].open_time != cursor:
                    raise FeedError(f"Unavailable {state.interval} candle at {cursor} for {state.symbol}")
            for bar in bars:
                if bar.open_time != cursor:
                    raise FeedError(
                        f"Non-contiguous REST data for {state.symbol} {state.interval} at {cursor}"
                    )
                state.add(bar, "rest_backfill")
                cursor += state.interval_ms
            LOGGER.info("%s %s recovered %d closed candles", state.symbol, state.interval, len(bars))

    def synchronize_interval(self, interval: str) -> None:
        boundary = self.rest.boundary(interval)
        for (symbol, state_interval), state in self.states.items():
            if state_interval == interval:
                self.synchronize(state, boundary)

    def synchronize_all(self) -> None:
        for interval in self.intervals:
            self.synchronize_interval(interval)

    def synchronize_spotgoods(self, state: SpotGoodsState, boundary: int) -> None:
        if state.last_open_time is None:
            bars = self.spot_rest.klines(state.symbol, boundary, limit=3)
            expected = list(range(
                boundary - 3 * SPOTGOODS_INTERVAL_MS,
                boundary,
                SPOTGOODS_INTERVAL_MS,
            ))
            if [bar.open_time for bar in bars] != expected:
                raise FeedError(
                    f"Expected 3 consecutive completed 1m spot bars for {state.symbol}"
                )
            for bar in bars:
                state.add(bar, "bootstrap")
            LOGGER.info("%s spot 1m initialized with 3 closed candles", state.symbol)
            return
        cursor = state.last_open_time + SPOTGOODS_INTERVAL_MS
        while cursor < boundary:
            bars = self.spot_rest.klines(state.symbol, boundary, start=cursor)
            if not bars or bars[0].open_time != cursor:
                raise FeedError(f"Unavailable spot 1m candle at {cursor} for {state.symbol}")
            for bar in bars:
                if bar.open_time != cursor:
                    raise FeedError(
                        f"Non-contiguous spot 1m data for {state.symbol} at {cursor}"
                    )
                state.add(bar, "rest_backfill")
                cursor += SPOTGOODS_INTERVAL_MS
            LOGGER.info("%s spot 1m recovered %d closed candles", state.symbol, len(bars))

    def synchronize_spotgoods_all(self) -> None:
        if not self.spotgoods_symbols:
            return
        available = self.spot_rest.available_symbols()
        symbols = [symbol for symbol in self.spotgoods_symbols if symbol in available]
        unavailable = set(self.spotgoods_symbols) - set(symbols)
        for symbol in sorted(unavailable):
            LOGGER.warning("Skipping %s: no active USDT spot market", symbol)
        self.spotgoods_states = {
            symbol: SpotGoodsState(symbol, self.output)
            for symbol in symbols
        }
        boundary = self.spot_rest.boundary()
        for state in self.spotgoods_states.values():
            self.synchronize_spotgoods(state, boundary)

    def synchronize_spotgoods_interval(self) -> None:
        boundary = self.spot_rest.boundary()
        for state in self.spotgoods_states.values():
            self.synchronize_spotgoods(state, boundary)

    def process(self, payload: dict) -> bool:
        event = payload.get("data", payload)
        if event.get("e") != "kline":
            return False
        candle = event["k"]
        interval = candle["i"]
        state = self.states.get((candle["s"], interval))
        if state is None or candle["x"] is not True:
            return False
        opening = int(candle["t"])
        if state.last_open_time is None:
            self.synchronize(state, opening)
        elif opening > state.last_open_time + state.interval_ms:
            self.synchronize(state, opening)
        added = state.handle_event(payload)
        if added:
            LOGGER.info("%s %s closed candle %d recorded and evaluated",
                        state.symbol, state.interval, opening)
        return added

    def process_spotgoods(self, payload: dict) -> bool:
        event = payload.get("data", payload)
        if event.get("e") != "kline":
            return False
        candle = event["k"]
        state = self.spotgoods_states.get(candle["s"])
        if state is None or candle["i"] != SPOTGOODS_INTERVAL or candle["x"] is not True:
            return False
        opening = int(candle["t"])
        if state.last_open_time is None:
            self.synchronize_spotgoods(state, opening)
        elif opening > state.last_open_time + SPOTGOODS_INTERVAL_MS:
            self.synchronize_spotgoods(state, opening)
        added = state.handle_event(payload)
        if added:
            LOGGER.info("%s spot 1m closed candle %d recorded and evaluated",
                        state.symbol, opening)
        return added

    def _stop_workers(self, failure=None) -> None:
        if failure is not None and self.failure is None:
            self.failure = failure
        self.stop_event.set()
        with self.connections_lock:
            connections = tuple(self.connections.values())
        for connection in connections:
            connection.close()

    def _run_interval(self, interval: str) -> None:
        from websocket import WebSocketApp

        symbols = [symbol for symbol, state_interval in self.states if state_interval == interval]
        streams = "/".join(f"{symbol.lower()}@kline_{interval}" for symbol in symbols)
        attempt = 0
        while not self.stop_event.is_set():
            worker_failure = [None]

            def on_open(connection) -> None:
                LOGGER.info("WebSocket connected for %s; checking missed candles", interval)
                try:
                    self.synchronize_interval(interval)
                except Exception as error:
                    worker_failure[0] = error
                    connection.close()

            def on_message(connection, message: str) -> None:
                try:
                    self.process(json.loads(message))
                except Exception as error:
                    worker_failure[0] = error
                    LOGGER.exception("Cannot process %s candle; closing stream", interval)
                    connection.close()

            def on_error(connection, error) -> None:
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    worker_failure[0] = error
                LOGGER.warning("WebSocket error for %s: %s", interval, error)

            connection = WebSocketApp(
                STREAM_URL + streams,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=lambda connection, status, message: LOGGER.warning(
                    "%s WebSocket closed: %s %s", interval, status, message),
            )
            with self.connections_lock:
                self.connections[interval] = connection
            if self.stop_event.is_set():
                connection.close()
                return
            connected_at = time.monotonic()
            try:
                connection.run_forever(ping_interval=120, ping_timeout=20)
            finally:
                connection.close()
                with self.connections_lock:
                    if self.connections.get(interval) is connection:
                        self.connections.pop(interval)
            failure = worker_failure[0]
            if failure is not None and not isinstance(failure, FeedError):
                self._stop_workers(failure)
                return
            if failure is not None:
                LOGGER.warning("%s recovery failed: %s", interval, failure)
            if self.stop_event.is_set():
                return
            if time.monotonic() - connected_at > 60:
                attempt = 0
            delay = min(2 ** min(attempt, 6), 60) + random.uniform(0, 1)
            attempt += 1
            LOGGER.info("Reconnecting %s in %.1f seconds", interval, delay)
            if self.stop_event.wait(delay):
                return

    def _run_spotgoods(self) -> None:
        from websocket import WebSocketApp

        symbols = list(self.spotgoods_states)
        streams = "/".join(
            f"{symbol.lower()}@kline_{SPOTGOODS_INTERVAL}" for symbol in symbols
        )
        attempt = 0
        while not self.stop_event.is_set():
            worker_failure = [None]

            def on_open(connection) -> None:
                LOGGER.info("Spot WebSocket connected; checking missed 1m candles")
                try:
                    self.synchronize_spotgoods_interval()
                except Exception as error:
                    worker_failure[0] = error
                    connection.close()

            def on_message(connection, message: str) -> None:
                try:
                    self.process_spotgoods(json.loads(message))
                except Exception as error:
                    worker_failure[0] = error
                    LOGGER.exception("Cannot process spot 1m candle; closing stream")
                    connection.close()

            def on_error(connection, error) -> None:
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    worker_failure[0] = error
                LOGGER.warning("Spot WebSocket error: %s", error)

            connection = WebSocketApp(
                SPOT_STREAM_URL + streams,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=lambda connection, status, message: LOGGER.warning(
                    "Spot WebSocket closed: %s %s", status, message),
            )
            with self.connections_lock:
                self.connections["spotgoods"] = connection
            if self.stop_event.is_set():
                connection.close()
                return
            connected_at = time.monotonic()
            try:
                connection.run_forever(ping_interval=120, ping_timeout=20)
            finally:
                connection.close()
                with self.connections_lock:
                    if self.connections.get("spotgoods") is connection:
                        self.connections.pop("spotgoods")
            failure = worker_failure[0]
            if failure is not None and not isinstance(failure, FeedError):
                self._stop_workers(failure)
                return
            if failure is not None:
                LOGGER.warning("Spot recovery failed: %s", failure)
            if self.stop_event.is_set():
                return
            if time.monotonic() - connected_at > 60:
                attempt = 0
            delay = min(2 ** min(attempt, 6), 60) + random.uniform(0, 1)
            attempt += 1
            LOGGER.info("Reconnecting spot stream in %.1f seconds", delay)
            if self.stop_event.wait(delay):
                return

    def _refresh_repeat_signals(self) -> None:
        while not self.stop_event.wait(1):
            try:
                self.repeat_signals.refresh()
            except Exception as error:
                LOGGER.exception("Cannot refresh repeat signals; stopping monitor")
                self._stop_workers(error)
                return

    def run(self) -> None:
        from websocket import setdefaulttimeout

        setdefaulttimeout(20)
        self.failure = None
        self.stop_event.clear()
        workers = [
            threading.Thread(target=self._run_interval, args=(interval,), name=f"monitor-{interval}")
            for interval in self.intervals
        ]
        if self.spotgoods_states:
            workers.append(threading.Thread(target=self._run_spotgoods, name="monitor-spotgoods"))
        refresh_worker = threading.Thread(target=self._refresh_repeat_signals,
                                          name="repeat-signals-refresh")
        refresh_worker.start()
        for worker in workers:
            worker.start()
        try:
            for worker in workers:
                worker.join()
        except KeyboardInterrupt as error:
            self._stop_workers(error)
            for worker in workers:
                worker.join()
        finally:
            self.stop_event.set()
            refresh_worker.join()
        if self.failure is not None:
            raise self.failure


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Record closed Binance contract and spot candles and evaluate configured strategies"
    )
    config_path = Path(__file__).resolve().with_name("Contract.json")
    try:
        with config_path.open(encoding="utf-8") as config_file:
            monitor_config = json.load(config_file)["monitor"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        parser.error(f"Cannot load monitor settings from {config_path}: {error}")
    if not isinstance(monitor_config, dict) or not isinstance(monitor_config.get("symbols"), list):
        parser.error(f"Invalid monitor settings in {config_path}: 'symbols' must be a list")
    intervals = monitor_config.get("intervals", ["15m"])
    if (not isinstance(intervals, list) or not intervals or
            any(interval not in INTERVAL_MS_BY_INTERVAL for interval in intervals)):
        parser.error(f"Invalid monitor intervals in {config_path}: choose from {SUPPORTED_INTERVALS}")
    spotgoods_config = monitor_config.get("spotgoods", {})
    if not isinstance(spotgoods_config, dict):
        parser.error(f"Invalid spotgoods settings in {config_path}: expected an object")
    spotgoods_enabled = spotgoods_config.get("enabled", False)
    spotgoods_symbols = spotgoods_config.get("symbols")
    if (not isinstance(spotgoods_enabled, bool) or
            (spotgoods_symbols is not None and not isinstance(spotgoods_symbols, list))):
        parser.error(f"Invalid spotgoods settings in {config_path}")
    output = Path(monitor_config.get("output", "data"))
    if not output.is_absolute():
        output = Path(__file__).resolve().parent / output
    parser.add_argument("--symbols", nargs="+", default=monitor_config["symbols"])
    parser.add_argument("--output", type=Path, default=output)
    bootstrap_group = parser.add_mutually_exclusive_group()
    bootstrap_group.add_argument("--bootstrap-only", dest="bootstrap_only", action="store_true",
                                 help="REST initialization only, then exit")
    bootstrap_group.add_argument("--no-bootstrap-only", dest="bootstrap_only", action="store_false",
                                 help="Run the WebSocket monitor after initialization")
    parser.set_defaults(bootstrap_only=bool(monitor_config.get("bootstrap_only", False)))
    arguments = parser.parse_args()
    arguments.symbols = list(dict.fromkeys(symbol.upper() for symbol in arguments.symbols))
    arguments.intervals = tuple(dict.fromkeys(intervals))
    if any(not symbol.isascii() or not symbol.isalnum() or not symbol.endswith("USDT")
           for symbol in arguments.symbols):
        parser.error("Symbols must be alphanumeric USDT pairs, e.g. MAGICUSDT")
    selected_spot_symbols = spotgoods_symbols or arguments.symbols
    if any(not isinstance(symbol, str) or not symbol.isascii() or not symbol.isalnum()
           or not symbol.endswith("USDT") for symbol in selected_spot_symbols):
        parser.error("Spotgoods symbols must be alphanumeric USDT pairs, e.g. BTCUSDT")
    arguments.spotgoods_symbols = (
        tuple(dict.fromkeys(symbol.upper() for symbol in selected_spot_symbols))
        if spotgoods_enabled else ()
    )
    return arguments


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    arguments = parse_arguments()
    arguments.output.mkdir(parents=True, exist_ok=True)
    from filelock import FileLock, Timeout

    try:
        with FileLock(str(arguments.output / ".monitor.lock"), timeout=0):
            monitor = Monitor(
                arguments.symbols,
                arguments.output,
                intervals=arguments.intervals,
                spotgoods_symbols=arguments.spotgoods_symbols,
            )
            monitor.synchronize_all()
            monitor.synchronize_spotgoods_all()
            if not arguments.bootstrap_only:
                monitor.run()
    except Timeout:
        raise SystemExit("Another monitor is already writing to this output directory")
    except KeyboardInterrupt:
        LOGGER.info("Monitor stopped")


if __name__ == "__main__":
    main()