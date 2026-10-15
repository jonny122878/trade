import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


INTERVAL_MS = 15 * 60 * 1000
TAIWAN_TZ = timezone(timedelta(hours=8))


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

    def record(self) -> dict:
        return {
            "symbol": self.symbol,
            "interval": "15m",
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
        return cls(**{field: record[field] for field in cls.__dataclass_fields__})

    @classmethod
    def from_rest(cls, symbol: str, row: list) -> "Bar":
        return cls(symbol, int(row[0]), int(row[6]), *map(str, row[1:5]))

    @classmethod
    def from_event(cls, event: dict) -> "Bar":
        return cls(
            event["s"], int(event["t"]), int(event["T"]),
            event["o"], event["h"], event["l"], event["c"],
        )


def evaluate(bars: list[Bar]) -> dict:
    result = {
        "symbol": bars[-1].symbol if bars else None,
        "interval": "15m",
        "evaluated_bar_open_time": bars[-1].open_time if bars else None,
        "rules_version": 1,
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
    if len({bar.symbol for bar in window}) != 1:
        raise ValueError("Strategy window must contain only one symbol")
    if any(
        following.open_time - previous.open_time != INTERVAL_MS
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
        "second_breakout_close": closes[1] > upper,
        "third_back_inside_zone": lower <= closes[2] <= upper,
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


class SymbolState:
    def __init__(self, symbol: str, root: Path):
        self.symbol = symbol
        self.directory = root / symbol
        self.directory.mkdir(parents=True, exist_ok=True)
        self.candle_path = self.directory / "15k.txt"
        self.strategy_path = self.directory / "strategy.txt"
        self.bars: list[Bar] = []
        self.last_evaluated = None
        for record in read_records(self.candle_path):
            bar = Bar.from_record(record)
            if bar.symbol != symbol:
                raise ValueError(f"Unexpected symbol in {self.candle_path}")
            if self.bars and bar.open_time <= self.bars[-1].open_time:
                raise ValueError(f"Unordered bars in {self.candle_path}")
            self.bars = (self.bars + [bar])[-12:]
        for record in read_records(self.strategy_path):
            self.last_evaluated = record["evaluated_bar_open_time"]
        self.evaluate_latest("recovery")

    @property
    def last_open_time(self):
        return self.bars[-1].open_time if self.bars else None

    def add(self, bar: Bar, source: str, calculate: bool = True) -> bool:
        if bar.symbol != self.symbol:
            raise ValueError("Cannot mix symbols")
        if self.last_open_time is not None and bar.open_time <= self.last_open_time:
            return False
        if self.last_open_time is not None and bar.open_time != self.last_open_time + INTERVAL_MS:
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
        self.last_evaluated = self.last_open_time

    def handle_event(self, payload: dict) -> bool:
        event = payload.get("data", payload)
        if event.get("e") != "kline":
            return False
        candle = event["k"]
        if candle["s"] != self.symbol or candle["i"] != "15m" or candle["x"] is not True:
            return False
        return self.add(Bar.from_event(candle), "websocket")