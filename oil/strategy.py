import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Sequence


ONE_MINUTE_MS = 60_000
FIVE_MINUTE_MS = 300_000
NEWS_LOOKBACK = timedelta(hours=24)
PRICE_MOVE_THRESHOLD = 0.005
FIRST_CLOSE_RATIO_THRESHOLD = 0.5
MAX_DEDUPE_KEYS = 10_000


@dataclass(frozen=True)
class Candle:
    symbol: str
    interval: str
    start_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    summary: str = ""
    published_at: str = ""
    url: str = ""


NewsQuery = Callable[
    [datetime, datetime], Awaitable[Sequence[NewsItem] | None]
]


@dataclass
class Candidate:
    trigger: Candle
    next_5m_start_ms: int
    news: tuple[NewsItem, ...]
    first_5m: Candle | None = None
    first_ratio: float | None = None


@dataclass(frozen=True)
class EntrySignal:
    symbol: str
    trigger: Candle
    first_5m: Candle
    second_5m: Candle
    first_ratio: float
    news: tuple[NewsItem, ...]


async def unavailable_news_query(
    _start_utc: datetime, _end_utc: datetime
) -> None:
    """Placeholder until a permitted news provider is selected."""
    return None


class StrategyEngine:
    def __init__(
        self,
        news_query: NewsQuery = unavailable_news_query,
        now: Callable[[], datetime] | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        self.news_query = news_query
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.log = log or logging.getLogger(__name__)
        self.candidates: list[Candidate] = []
        self.latest_5m_start_by_symbol: dict[str, int] = {}
        self._seen_keys: set[tuple[str, str, int]] = set()
        self._seen_order: deque[tuple[str, str, int]] = deque()

    def has_seen(self, candle: Candle) -> bool:
        return (candle.symbol, candle.interval, candle.start_ms) in self._seen_keys

    def _is_duplicate(self, candle: Candle) -> bool:
        key = (candle.symbol, candle.interval, candle.start_ms)
        if key in self._seen_keys:
            return True
        self._seen_keys.add(key)
        self._seen_order.append(key)
        if len(self._seen_order) > MAX_DEDUPE_KEYS:
            self._seen_keys.discard(self._seen_order.popleft())
        return False

    async def on_1m(self, candle: Candle) -> None:
        if candle.interval != "1" or self._is_duplicate(candle):
            return
        if candle.open <= 0 or candle.high < candle.open * (
            1 + PRICE_MOVE_THRESHOLD
        ):
            return

        end_utc = self.now()
        if end_utc.tzinfo is None:
            end_utc = end_utc.replace(tzinfo=timezone.utc)
        start_utc = end_utc - NEWS_LOOKBACK
        try:
            news = await self.news_query(start_utc, end_utc)
        except Exception:
            self.log.exception(
                "NEWS_QUERY_FAILED %s trigger_start=%s",
                candle.symbol,
                candle.start_ms,
            )
            return

        if news is None:
            self.log.warning(
                "CANDIDATE_CANCELLED %s trigger_start=%s reason=news_unavailable",
                candle.symbol,
                candle.start_ms,
            )
            return
        if not news:
            self.log.info(
                "CANDIDATE_CANCELLED %s trigger_start=%s reason=no_matching_news",
                candle.symbol,
                candle.start_ms,
            )
            return

        latest_5m_start = self.latest_5m_start_by_symbol.get(candle.symbol)
        if latest_5m_start is None:
            next_5m_start = candle.start_ms // FIVE_MINUTE_MS * FIVE_MINUTE_MS
        else:
            next_5m_start = latest_5m_start + FIVE_MINUTE_MS

        self.candidates.append(
            Candidate(
                trigger=candle,
                next_5m_start_ms=next_5m_start,
                news=tuple(news),
            )
        )
        self.log.info(
            "CANDIDATE_CREATED %s trigger_start=%s high=%s news_matches=%s",
            candle.symbol,
            candle.start_ms,
            candle.high,
            len(news),
        )

    def on_5m(self, candle: Candle) -> list[EntrySignal]:
        if candle.interval != "5" or self._is_duplicate(candle):
            return []

        previous_start = self.latest_5m_start_by_symbol.get(candle.symbol)
        if previous_start is not None and candle.start_ms <= previous_start:
            self.log.warning(
                "OUT_OF_ORDER_5M %s start=%s latest=%s",
                candle.symbol,
                candle.start_ms,
                previous_start,
            )
            return []
        self.latest_5m_start_by_symbol[candle.symbol] = candle.start_ms

        signals: list[EntrySignal] = []
        active: list[Candidate] = []
        for candidate in self.candidates:
            if candidate.trigger.symbol != candle.symbol:
                active.append(candidate)
                continue
            if candle.start_ms < candidate.next_5m_start_ms:
                active.append(candidate)
                continue
            if candle.start_ms > candidate.next_5m_start_ms:
                self.log.warning(
                    "CANDIDATE_CANCELLED %s trigger_start=%s reason=missed_5m expected=%s received=%s",
                    candle.symbol,
                    candidate.trigger.start_ms,
                    candidate.next_5m_start_ms,
                    candle.start_ms,
                )
                continue

            if candidate.first_5m is None:
                ratio = candle.close / candidate.trigger.high
                if ratio < FIRST_CLOSE_RATIO_THRESHOLD:
                    self.log.info(
                        "CANDIDATE_CANCELLED %s trigger_start=%s reason=first_close_ratio ratio=%.8f",
                        candle.symbol,
                        candidate.trigger.start_ms,
                        ratio,
                    )
                    continue
                candidate.first_5m = candle
                candidate.first_ratio = ratio
                candidate.next_5m_start_ms += FIVE_MINUTE_MS
                active.append(candidate)
                continue

            if candle.close > candidate.trigger.high:
                signals.append(
                    EntrySignal(
                        symbol=candle.symbol,
                        trigger=candidate.trigger,
                        first_5m=candidate.first_5m,
                        second_5m=candle,
                        first_ratio=candidate.first_ratio or 0.0,
                        news=candidate.news,
                    )
                )
                self.log.info(
                    "ENTRY_SIGNAL %s trigger_start=%s second_5m_start=%s close=%s",
                    candle.symbol,
                    candidate.trigger.start_ms,
                    candle.start_ms,
                    candle.close,
                )
            else:
                self.log.info(
                    "CANDIDATE_CANCELLED %s trigger_start=%s reason=second_close_not_above_high close=%s high=%s",
                    candle.symbol,
                    candidate.trigger.start_ms,
                    candle.close,
                    candidate.trigger.high,
                )

        self.candidates = active
        return signals