import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


INTERVAL_MS_BY_INTERVAL = {
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
}
SUPPORTED_INTERVALS = tuple(INTERVAL_MS_BY_INTERVAL)
INTERVAL_MS = INTERVAL_MS_BY_INTERVAL["15m"]
TAIWAN_TZ = timezone(timedelta(hours=8))
_RECORD_LOCK = threading.Lock()


def format_time_tw(timestamp: int) -> str:
    seconds, milliseconds = divmod(timestamp, 1000)
    formatted = datetime.fromtimestamp(seconds, tz=TAIWAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return f"{formatted}.{milliseconds:03d}" if milliseconds else formatted


@dataclass(frozen=True)
class Bar:
    symbol: str
    open_time: int
    close_time: int
    open: str
    high: str
    low: str
    close: str
    interval: str = "15m"

    def record(self) -> dict:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time": self.open_time,
            "close_time": self.close_time,
            "open_time_tw": format_time_tw(self.open_time),
            "close_time_tw": format_time_tw(self.close_time),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "candle": False,
            "is_closed": True,
        }

    @classmethod
    def from_record(cls, record: dict) -> "Bar":
        return cls(
            record["symbol"], record["open_time"], record["close_time"],
            record["open"], record["high"], record["low"], record["close"],
            record.get("interval", "15m"),
        )

    @classmethod
    def from_rest(cls, symbol: str, row: list, interval: str = "15m") -> "Bar":
        return cls(symbol, int(row[0]), int(row[6]), *map(str, row[1:5]), interval)

    @classmethod
    def from_event(cls, event: dict) -> "Bar":
        return cls(
            event["s"], int(event["t"]), int(event["T"]),
            event["o"], event["h"], event["l"], event["c"], event["i"],
        )


def evaluate(bars: list[Bar]) -> dict:
    result = {
        "symbol": bars[-1].symbol if bars else None,
        "interval": bars[-1].interval if bars else "15m",
        "evaluated_bar_open_time": bars[-1].open_time if bars else None,
        "rules_version": 2,
        "pressure_lower": None,
        "pressure_upper": None,
        "pressure_bar_open_times": [],
        "signal_bar_open_times": [],
        "conditions": {},
        "short_signal": False,
        "reason": "insufficient_bars",
    }
    if len(bars) < 12:
        return result
    window = bars[-12:]
    if len({bar.symbol for bar in window}) != 1 or len({bar.interval for bar in window}) != 1:
        raise ValueError("Strategy window must contain only one symbol and interval")
    interval_ms = INTERVAL_MS_BY_INTERVAL.get(window[-1].interval)
    if interval_ms is None:
        result["reason"] = "unsupported_interval"
        return result
    if any(
        following.open_time - previous.open_time != interval_ms
        for previous, following in zip(window, window[1:])
    ):
        result["reason"] = "non_contiguous_bars"
        return result
    candidates = sorted(
        (bar for bar in window[:8] if Decimal(bar.close) < Decimal(bar.high)),
        key=lambda bar: (Decimal(bar.close), bar.open_time),
    )
    best_group: list[Bar] = []
    best_score = (0, ())
    for start, first in enumerate(candidates):
        group = [
            bar for bar in candidates[start:]
            if Decimal(bar.close) / Decimal(first.close) - 1 <= Decimal("0.01")
        ]
        score = (len(group), tuple(sorted((bar.open_time for bar in group), reverse=True)))
        if score > best_score:
            best_group, best_score = group, score
    if len(best_group) < 2:
        result["reason"] = "insufficient_pressure_candidates"
        return result
    lower = min(Decimal(bar.high) for bar in best_group)
    upper = max(Decimal(bar.high) for bar in best_group)
    signal_bars = window[8:]
    closes = [Decimal(bar.close) for bar in signal_bars]
    conditions = {
        "first_below_zone": closes[0] < lower,
        "second_wick_breaks_upper": Decimal(signal_bars[1].high) > upper,
        "second_inside_zone": lower <= closes[1] <= upper,
        "third_inside_zone": lower <= closes[2] <= upper,
        "second_close_above_third": closes[1] > closes[2],
        "fourth_below_zone": closes[3] < lower,
    }
    matched = all(conditions.values())
    result.update(
        pressure_lower=str(lower),
        pressure_upper=str(upper),
        pressure_bar_open_times=sorted(bar.open_time for bar in best_group),
        signal_bar_open_times=[bar.open_time for bar in signal_bars],
        conditions=conditions,
        short_signal=matched,
        reason="short_signal_candidate" if matched else "conditions_not_met",
    )
    return result


def append_record(path: Path, record: dict) -> None:
    with _RECORD_LOCK:
        with path.open("a", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
            output.flush()


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON in {path}, line {line_number}") from error
    return records


class RepeatSignals:
    def __init__(self, root: Path, keys: set[tuple[str, str]], clock=None):
        self.path = root / "repeat_signals.txt"
        self.keys = keys
        self.clock = clock if clock is not None else lambda: time.time_ns() // 1_000_000
        self.lock = threading.Lock()
        self.latest: dict[tuple[str, str], dict] = {}
        root.mkdir(parents=True, exist_ok=True)
        for record in read_records(root / "signals.txt"):
            self._remember(record)
        self.refresh()

    def _remember(self, record: dict) -> None:
        key = (record["symbol"], record.get("interval", "15m"))
        if key not in self.keys:
            return
        previous = self.latest.get(key)
        if previous is None or record["evaluated_bar_open_time"] >= previous["evaluated_bar_open_time"]:
            self.latest[key] = dict(record)

    def update(self, record: dict) -> None:
        with self.lock:
            self._remember(record)
            self._refresh()

    def refresh(self) -> None:
        with self.lock:
            self._refresh()

    def _refresh(self) -> None:
        now = self.clock()
        grouped: dict[str, list[dict]] = {}
        for (symbol, interval), record in self.latest.items():
            interval_ms = INTERVAL_MS_BY_INTERVAL[interval]
            opening = record["evaluated_bar_open_time"]
            if (not record["short_signal"] or record.get("source") != "websocket" or
                    opening != now // interval_ms * interval_ms - interval_ms):
                continue
            confirmed = opening + interval_ms
            expires = confirmed + interval_ms
            grouped.setdefault(symbol, []).append({
                "interval": interval,
                "evaluated_bar_open_time": opening,
                "evaluated_bar_open_time_tw": format_time_tw(opening),
                "confirmed_at": confirmed,
                "confirmed_at_tw": format_time_tw(confirmed),
                "expires_at": expires,
                "expires_at_tw": format_time_tw(expires),
                "source": record["source"],
            })
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as output:
                for symbol, signals in sorted(grouped.items()):
                    if len(signals) < 2:
                        continue
                    signals.sort(key=lambda signal: INTERVAL_MS_BY_INTERVAL[signal["interval"]])
                    expires = min(signal["expires_at"] for signal in signals)
                    summary = {
                        "symbol": symbol,
                        "direction": "short",
                        "total_count": len(signals),
                        "distinct_interval_count": len(signals),
                        "intervals": [signal["interval"] for signal in signals],
                        "generated_at": now,
                        "generated_at_tw": format_time_tw(now),
                        "expires_at": expires,
                        "expires_at_tw": format_time_tw(expires),
                        "signals": signals,
                    }
                    output.write(json.dumps(summary, ensure_ascii=True, allow_nan=False) + "\n")
            for attempt in range(5):
                try:
                    temporary.replace(self.path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.1 * (attempt + 1))
        finally:
            temporary.unlink(missing_ok=True)


class SymbolState:
    def __init__(self, symbol: str, root: Path, interval: str = "15m", repeat_signals=None):
        if interval not in INTERVAL_MS_BY_INTERVAL:
            raise ValueError(f"Unsupported interval: {interval}")
        self.symbol = symbol
        self.interval = interval
        self.interval_ms = INTERVAL_MS_BY_INTERVAL[interval]
        self.directory = root / symbol
        self.directory.mkdir(parents=True, exist_ok=True)
        self.candle_path = self.directory / ("15k.txt" if interval == "15m" else f"candles_{interval}.txt")
        self.strategy_path = self.directory / ("strategy.txt" if interval == "15m" else f"strategy_{interval}.txt")
        self.signal_path = root / "signals.txt"
        self.repeat_signals = repeat_signals
        self.bars: list[Bar] = []
        self.last_evaluated = None
        for record in read_records(self.candle_path):
            bar = Bar.from_record(record)
            if bar.symbol != symbol or bar.interval != interval:
                raise ValueError(f"Unexpected symbol or interval in {self.candle_path}")
            if self.bars and bar.open_time <= self.bars[-1].open_time:
                raise ValueError(f"Unordered bars in {self.candle_path}")
            self.bars = (self.bars + [bar])[-12:]
        latest_record = None
        for record in read_records(self.strategy_path):
            self.last_evaluated = record["evaluated_bar_open_time"]
            latest_record = record
        if self.repeat_signals is not None and latest_record is not None:
            self.repeat_signals.update(latest_record)
        self.evaluate_latest("recovery")

    @property
    def last_open_time(self):
        return self.bars[-1].open_time if self.bars else None

    def add(self, bar: Bar, source: str, calculate: bool = True) -> bool:
        if bar.symbol != self.symbol or bar.interval != self.interval:
            raise ValueError("Cannot mix symbols or intervals")
        if self.last_open_time is not None and bar.open_time <= self.last_open_time:
            return False
        if self.last_open_time is not None and bar.open_time != self.last_open_time + self.interval_ms:
            raise ValueError(f"Missing candles before {bar.open_time} for {self.symbol}")
        record = bar.record()
        record["source"] = source
        append_record(self.candle_path, record)
        self.bars = (self.bars + [bar])[-12:]
        if calculate:
            self.evaluate_latest(source)
        return True

    def evaluate_latest(self, source: str) -> None:
        if len(self.bars) < 12 or self.last_evaluated == self.last_open_time:
            return
        record = evaluate(self.bars)
        record["source"] = source
        append_record(self.strategy_path, record)
        if record["short_signal"]:
            append_record(self.signal_path, record)
        if self.repeat_signals is not None:
            self.repeat_signals.update(record)
        self.last_evaluated = self.last_open_time

    def handle_event(self, payload: dict) -> bool:
        event = payload.get("data", payload)
        if event.get("e") != "kline":
            return False
        candle = event["k"]
        if candle["s"] != self.symbol or candle["i"] != self.interval or candle["x"] is not True:
            return False
        return self.add(Bar.from_event(candle), "websocket")