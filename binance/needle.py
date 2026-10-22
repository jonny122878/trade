import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path


LOGGER = logging.getLogger("binance.needle")
INTERVAL = "15m"
INTERVAL_MS = 15 * 60 * 1000
BAR_COUNT = 5
STREAM_URL = "wss://fstream.binance.com/market/stream?streams="
CONFIG_PATH = Path(__file__).resolve().with_name("Contract.json")
OUTPUT_PATH = Path(__file__).resolve().with_name("data") / "needle.txt"
_OUTPUT_LOCK = threading.Lock()


@dataclass(frozen=True)
class Candle:
	symbol: str
	open_time: int
	close_time: int
	open: Decimal
	close: Decimal

	@classmethod
	def from_event(cls, symbol: str, event: dict) -> "Candle":
		try:
			opening = Decimal(str(event["o"]))
			closing = Decimal(str(event["c"]))
			open_time = int(event["t"])
			close_time = int(event["T"])
		except (KeyError, TypeError, ValueError, InvalidOperation) as error:
			raise ValueError("Invalid closed kline event") from error
		if not opening.is_finite() or not closing.is_finite():
			raise ValueError("Candle prices must be finite")
		return cls(symbol, open_time, close_time, opening, closing)


def load_symbols(config_path: Path = CONFIG_PATH) -> list[str]:
	try:
		with config_path.open(encoding="utf-8") as source:
			config = json.load(source)
		symbols = config["monitor"]["symbols"]
	except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
		raise ValueError(f"Cannot load monitor symbols from {config_path}: {error}") from error
	if not isinstance(symbols, list) or not symbols:
		raise ValueError("Contract.json monitor.symbols must be a non-empty list")

	normalized = []
	for symbol in symbols:
		if (not isinstance(symbol, str) or not symbol.isascii() or
				not symbol.isalnum() or not symbol.endswith("USDT")):
			raise ValueError(f"Invalid USDT contract symbol: {symbol!r}")
		normalized.append(symbol.upper())
	return list(dict.fromkeys(normalized))


def build_stream_url(symbols: list[str]) -> str:
	streams = "/".join(f"{symbol.lower()}@kline_{INTERVAL}" for symbol in symbols)
	return STREAM_URL + streams


def evaluate_window(candles: list[Candle]) -> dict | None:
	if len(candles) != BAR_COUNT:
		return None
	if len({candle.symbol for candle in candles}) != 1:
		return None
	if any(
		current.open_time - previous.open_time != INTERVAL_MS
		for previous, current in zip(candles, candles[1:])
	):
		return None

	green_count = sum(candle.close >= candle.open for candle in candles)
	red_count = sum(candle.close < candle.open for candle in candles)
	if not (green_count == 5 or (green_count == 4 and red_count == 1)):
		return None

	latest = candles[-1]
	return {
		"strategy_id": "needle",
		"symbol": latest.symbol,
		"interval": INTERVAL,
		"direction": "short",
		"evaluated_bar_open_time": latest.open_time,
		"evaluated_bar_close_time": latest.close_time,
		"green_count": green_count,
		"red_count": red_count,
		"candle_open_times": [candle.open_time for candle in candles],
		"source": "websocket",
	}


def append_signal(path: Path, signal: dict) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with _OUTPUT_LOCK:
		with path.open("a", encoding="utf-8", newline="\n") as output:
			output.write(json.dumps(signal, ensure_ascii=True, allow_nan=False) + "\n")
			output.flush()


def append_candle(path: Path, candle: Candle) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	record = {
		"symbol": candle.symbol,
		"interval": INTERVAL,
		"open_time": candle.open_time,
		"close_time": candle.close_time,
		"open": str(candle.open),
		"close": str(candle.close),
		"candle_color": "綠K" if candle.close >= candle.open else "紅K",
	}
	with _OUTPUT_LOCK:
		with path.open("a", encoding="utf-8", newline="\n") as output:
			output.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
			output.flush()


class SymbolWindow:
	def __init__(self):
		self.candles: deque[Candle] = deque(maxlen=BAR_COUNT)
		self.last_open_time = None

	def add(self, candle: Candle) -> bool:
		if self.last_open_time is not None and candle.open_time <= self.last_open_time:
			return False
		if (self.last_open_time is not None and
				candle.open_time - self.last_open_time != INTERVAL_MS):
			self.candles.clear()
		self.candles.append(candle)
		self.last_open_time = candle.open_time
		return True


class NeedleScanner:
	def __init__(self, symbols: list[str], output_path: Path = OUTPUT_PATH):
		self.symbols = tuple(dict.fromkeys(symbol.upper() for symbol in symbols))
		self.output_path = Path(output_path)
		self.output_path.parent.mkdir(parents=True, exist_ok=True)
		self.output_path.touch(exist_ok=True)
		self.candle_output_dir = self.output_path.parent
		self.windows = {symbol: SymbolWindow() for symbol in self.symbols}
		self.stop_event = threading.Event()

	@property
	def stream_url(self) -> str:
		return build_stream_url(list(self.symbols))

	def process_payload(self, payload: dict) -> dict | None:
		event = payload.get("data", payload)
		if not isinstance(event, dict) or event.get("e") != "kline":
			return None
		kline = event.get("k")
		if not isinstance(kline, dict) or kline.get("x") is not True:
			return None
		symbol = kline.get("s")
		if not isinstance(symbol, str) or symbol not in self.windows or kline.get("i") != INTERVAL:
			return None

		try:
			candle = Candle.from_event(symbol, kline)
		except ValueError as error:
			LOGGER.warning("Ignoring invalid closed candle for %s: %s", symbol, error)
			return None

		window = self.windows[symbol]
		if not window.add(candle):
			return None
		append_candle(self.candle_output_dir / f"{symbol}_15k.txt", candle)
		signal = evaluate_window(list(window.candles))
		if signal is not None:
			append_signal(self.output_path, signal)
			LOGGER.info("Needle signal: %s at %d", symbol, candle.open_time)
		return signal

	def on_message(self, connection, message: str) -> None:
		try:
			self.process_payload(json.loads(message))
		except (json.JSONDecodeError, TypeError, AttributeError) as error:
			LOGGER.warning("Ignoring invalid WebSocket message: %s", error)

	def on_open(self, connection) -> None:
		LOGGER.info("Connected to Binance 15m futures stream for %d symbols", len(self.symbols))

	def on_error(self, connection, error) -> None:
		if isinstance(error, (KeyboardInterrupt, SystemExit)):
			self.stop_event.set()
			return
		LOGGER.warning("Needle WebSocket error: %s", error)

	def on_close(self, connection, status, message) -> None:
		LOGGER.warning("Needle WebSocket closed: %s %s", status, message)

	def run(self, websocket_app_factory=None) -> None:
		if websocket_app_factory is None:
			from websocket import WebSocketApp

			websocket_app_factory = WebSocketApp

		attempt = 0
		while not self.stop_event.is_set():
			connection = websocket_app_factory(
				self.stream_url,
				on_open=self.on_open,
				on_message=self.on_message,
				on_error=self.on_error,
				on_close=self.on_close,
			)
			connected_at = time.monotonic()
			try:
				connection.run_forever(ping_interval=120, ping_timeout=20)
			except (KeyboardInterrupt, SystemExit):
				self.stop_event.set()
				break
			if self.stop_event.is_set():
				break
			if time.monotonic() - connected_at > 60:
				attempt = 0
			delay = min(2 ** min(attempt, 6), 60)
			attempt += 1
			LOGGER.info("Reconnecting needle stream in %d seconds", delay)
			if self.stop_event.wait(delay):
				break


def main() -> None:
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s %(levelname)s %(name)s: %(message)s",
	)
	scanner = NeedleScanner(load_symbols())
	try:
		scanner.run()
	except KeyboardInterrupt:
		scanner.stop_event.set()
		LOGGER.info("Needle scanner stopped")


if __name__ == "__main__":
	main()
