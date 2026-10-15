import argparse
import json
import logging
import random
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from strategy import Bar, INTERVAL_MS, SymbolState


LOGGER = logging.getLogger("binance.monitor")
REST_URL = "https://fapi.binance.com"
STREAM_URL = "wss://fstream.binance.com/market/stream?streams="


class FeedError(RuntimeError):
    pass


class FuturesRest:
    def request(self, route: str, **parameters):
        url = REST_URL + route
        if parameters:
            url += "?" + urlencode(parameters)
        for attempt in range(5):
            delay = min(2 ** attempt, 30)
            try:
                request = Request(url, headers={"User-Agent": "binance-15m-monitor/1"})
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

    def boundary(self) -> int:
        server_time = int(self.request("/fapi/v1/time")["serverTime"])
        return server_time // INTERVAL_MS * INTERVAL_MS

    def klines(self, symbol: str, end: int, start=None, limit: int = 1000) -> list[Bar]:
        parameters = {"symbol": symbol, "interval": "15m", "endTime": end - 1, "limit": limit}
        if start is not None:
            parameters["startTime"] = start
        rows = self.request("/fapi/v1/klines", **parameters)
        return [Bar.from_rest(symbol, row) for row in rows
                if int(row[6]) < end and (start is None or int(row[0]) >= start)]


class Monitor:
    def __init__(self, symbols: list[str], output: Path, rest=None):
        self.rest = rest if rest is not None else FuturesRest()
        self.states = {symbol: SymbolState(symbol, output) for symbol in symbols}
        self.failure = None

    def synchronize(self, state: SymbolState, boundary: int) -> None:
        if state.last_open_time is None:
            bars = self.rest.klines(state.symbol, boundary, limit=12)
            expected = list(range(boundary - 12 * INTERVAL_MS, boundary, INTERVAL_MS))
            if [bar.open_time for bar in bars] != expected:
                raise FeedError(f"Expected 12 consecutive completed bars for {state.symbol}")
            for bar in bars:
                state.add(bar, "bootstrap", calculate=False)
            state.evaluate_latest("bootstrap")
            LOGGER.info("%s initialized with 12 closed candles", state.symbol)
            return
        cursor = state.last_open_time + INTERVAL_MS
        while cursor < boundary:
            bars = self.rest.klines(state.symbol, boundary, start=cursor)
            if not bars or bars[0].open_time != cursor:
                raise FeedError(f"Unavailable candle at {cursor} for {state.symbol}")
            for bar in bars:
                if bar.open_time != cursor:
                    raise FeedError(f"Non-contiguous REST data for {state.symbol} at {cursor}")
                state.add(bar, "rest_backfill")
                cursor += INTERVAL_MS
            LOGGER.info("%s recovered %d closed candles", state.symbol, len(bars))

    def synchronize_all(self) -> None:
        boundary = self.rest.boundary()
        for state in self.states.values():
            self.synchronize(state, boundary)

    def process(self, payload: dict) -> bool:
        event = payload.get("data", payload)
        if event.get("e") != "kline":
            return False
        candle = event["k"]
        state = self.states.get(candle["s"])
        if state is None or candle["i"] != "15m" or candle["x"] is not True:
            return False
        opening = int(candle["t"])
        if state.last_open_time is None:
            self.synchronize(state, opening)
        elif opening > state.last_open_time + INTERVAL_MS:
            self.synchronize(state, opening)
        added = state.handle_event(payload)
        if added:
            LOGGER.info("%s closed candle %d recorded and evaluated", state.symbol, opening)
        return added

    def on_open(self, connection) -> None:
        LOGGER.info("WebSocket connected; checking missed candles")
        try:
            self.synchronize_all()
        except Exception as error:
            self.failure = error
            connection.close()

    def on_message(self, connection, message: str) -> None:
        try:
            self.process(json.loads(message))
        except Exception as error:
            self.failure = error
            LOGGER.exception("Cannot process candle; closing stream")
            connection.close()

    def on_error(self, connection, error) -> None:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            self.failure = error
        LOGGER.warning("WebSocket error: %s", error)

    def run(self) -> None:
        from websocket import WebSocketApp, setdefaulttimeout

        setdefaulttimeout(20)
        streams = "/".join(f"{symbol.lower()}@kline_15m" for symbol in self.states)
        attempt = 0
        while True:
            self.failure = None
            connection = WebSocketApp(
                STREAM_URL + streams,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=lambda connection, status, message: LOGGER.warning(
                    "WebSocket closed: %s %s", status, message),
            )
            connected_at = time.monotonic()
            try:
                connection.run_forever(ping_interval=120, ping_timeout=20)
            finally:
                connection.close()
            if self.failure is not None and not isinstance(self.failure, FeedError):
                raise self.failure
            if self.failure is not None:
                LOGGER.warning("Recovery failed: %s", self.failure)
            if time.monotonic() - connected_at > 60:
                attempt = 0
            delay = min(2 ** min(attempt, 6), 60) + random.uniform(0, 1)
            attempt += 1
            LOGGER.info("Reconnecting in %.1f seconds", delay)
            time.sleep(delay)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Record closed Binance USD-M 15m candles and short signals")
    parser.add_argument("--symbols", nargs="+", default=["MAGICUSDT", "OGNUSDT", "GTCUSDT", "WUSDT", "BTWUSDT", "WALUSDT", "ARCUSDT"])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "data")
    parser.add_argument("--bootstrap-only", action="store_true", help="REST initialization only, then exit")
    arguments = parser.parse_args()
    arguments.symbols = list(dict.fromkeys(symbol.upper() for symbol in arguments.symbols))
    if any(not symbol.isascii() or not symbol.isalnum() or not symbol.endswith("USDT")
           for symbol in arguments.symbols):
        parser.error("Symbols must be alphanumeric USDT pairs, e.g. MAGICUSDT")
    if len(arguments.symbols) > 100:
        parser.error("At most 100 symbols per process")
    return arguments


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    arguments = parse_arguments()
    arguments.output.mkdir(parents=True, exist_ok=True)
    from filelock import FileLock, Timeout

    try:
        with FileLock(str(arguments.output / ".monitor.lock"), timeout=0):
            monitor = Monitor(arguments.symbols, arguments.output)
            monitor.synchronize_all()
            if not arguments.bootstrap_only:
                monitor.run()
    except Timeout:
        raise SystemExit("Another monitor is already writing to this output directory")
    except KeyboardInterrupt:
        LOGGER.info("Monitor stopped")


if __name__ == "__main__":
    main()