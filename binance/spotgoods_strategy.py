from decimal import Decimal
from pathlib import Path

from strategy import Bar, append_record, read_records


STRATEGY_ID = "spotgoods"
INTERVAL = "1m"
INTERVAL_MS = 60_000
RULES_VERSION = 1
REQUIRED_BARS = 3
MIN_HIGH_GAIN = Decimal("0.01")


def evaluate(bars: list[Bar]) -> dict:
    window = bars[-REQUIRED_BARS:]
    result = {
        "strategy_id": STRATEGY_ID,
        "market": "spot",
        "symbol": window[-1].symbol if window else None,
        "interval": INTERVAL,
        "direction": "long",
        "evaluated_bar_open_time": window[-1].open_time if window else None,
        "rules_version": RULES_VERSION,
        "parameters": {
            "required_consecutive_bars": REQUIRED_BARS,
            "minimum_high_gain": str(MIN_HIGH_GAIN),
            "minimum_high_gain_comparison": "strictly_greater_than",
        },
        "signal_bar_open_times": [bar.open_time for bar in window],
        "conditions": [],
        "long_signal": False,
        "reason": "insufficient_bars",
    }
    if len(window) < REQUIRED_BARS:
        return result
    if any(bar.symbol != window[-1].symbol or bar.interval != INTERVAL for bar in window):
        result["reason"] = "mixed_symbol_or_interval"
        return result
    if any(following.open_time - previous.open_time != INTERVAL_MS
           for previous, following in zip(window, window[1:])):
        result["reason"] = "non_contiguous_bars"
        return result

    conditions = []
    for bar in window:
        opening = Decimal(bar.open)
        if opening <= 0:
            result["reason"] = "invalid_open_price"
            return result
        conditions.append({
            "bar_open_time": bar.open_time,
            "green_candle": Decimal(bar.close) > opening,
            "high_gain_over_threshold": Decimal(bar.high) / opening - 1 > MIN_HIGH_GAIN,
        })
    matched = all(condition["green_candle"] and condition["high_gain_over_threshold"]
                  for condition in conditions)
    result.update(
        conditions=conditions,
        long_signal=matched,
        reason="long_signal_candidate" if matched else "conditions_not_met",
    )
    return result


class SpotGoodsState:
    def __init__(self, symbol: str, root: Path):
        self.symbol = symbol
        self.directory = root / symbol
        self.directory.mkdir(parents=True, exist_ok=True)
        self.candle_path = self.directory / "spot_1m.txt"
        self.strategy_path = self.directory / "spotgoods_strategy.txt"
        self.signal_path = root / "signals.txt"
        self.bars: list[Bar] = []
        self.last_evaluated = None
        self.previous_long_signal = False

        for record in read_records(self.candle_path):
            bar = Bar.from_record(record)
            if bar.symbol != symbol or bar.interval != INTERVAL:
                raise ValueError(f"Unexpected symbol or interval in {self.candle_path}")
            if self.bars and bar.open_time <= self.bars[-1].open_time:
                raise ValueError(f"Unordered bars in {self.candle_path}")
            self.bars = (self.bars + [bar])[-REQUIRED_BARS:]
        latest_record = None
        for record in read_records(self.strategy_path):
            self.last_evaluated = record["evaluated_bar_open_time"]
            latest_record = record
        if latest_record is not None:
            self.previous_long_signal = bool(latest_record.get("long_signal", False))
        self.evaluate_latest("recovery")

    @property
    def last_open_time(self):
        return self.bars[-1].open_time if self.bars else None

    def add(self, bar: Bar, source: str) -> bool:
        if bar.symbol != self.symbol or bar.interval != INTERVAL:
            raise ValueError("Cannot mix symbols or intervals")
        if self.last_open_time is not None and bar.open_time <= self.last_open_time:
            return False
        if (self.last_open_time is not None and
                bar.open_time != self.last_open_time + INTERVAL_MS):
            raise ValueError(f"Missing candles before {bar.open_time} for {self.symbol}")
        record = bar.record()
        record.update(market="spot", source=source)
        append_record(self.candle_path, record)
        self.bars = (self.bars + [bar])[-REQUIRED_BARS:]
        self.evaluate_latest(source)
        return True

    def evaluate_latest(self, source: str) -> None:
        if len(self.bars) < REQUIRED_BARS or self.last_evaluated == self.last_open_time:
            return
        record = evaluate(self.bars)
        record["source"] = source
        record["signal_emitted"] = record["long_signal"] and not self.previous_long_signal
        append_record(self.strategy_path, record)
        if record["signal_emitted"]:
            append_record(self.signal_path, record)
        self.previous_long_signal = record["long_signal"]
        self.last_evaluated = self.last_open_time

    def handle_event(self, payload: dict, source: str = "websocket") -> bool:
        event = payload.get("data", payload)
        if event.get("e") != "kline":
            return False
        candle = event["k"]
        if (candle["s"] != self.symbol or candle["i"] != INTERVAL or
                candle["x"] is not True):
            return False
        return self.add(Bar.from_event(candle), source)