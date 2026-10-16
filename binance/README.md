# Binance multi-interval strategy monitor

Records public USD-M USDT perpetual candles for the failed-breakout short
strategy and Binance spot candles for the `spotgoods` long strategy. No API key,
account access, or order submission. Requires Python 3.10 or newer and network
access to Binance.

## Setup and run

Run these commands in this directory with an installed Python interpreter:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe monitor.py
```

The monitor keeps running until stopped with Ctrl+C. To launch a separate
background process in Windows PowerShell:

```powershell
$process = Start-Process -FilePath "$PWD\.venv\Scripts\python.exe" -ArgumentList 'monitor.py' -WorkingDirectory $PWD -PassThru
$process.Id
```

Prefer Ctrl+C in an interactive terminal for a clean stop. For unattended use,
configure Windows Task Scheduler with this directory as the working directory.
Force termination during a file write can leave an incomplete JSON line.

The configured intervals are `5m`, `15m`, `1h`, and `4h`. Each interval uses a
combined WebSocket connection with independent state per symbol and interval:

```powershell
.\.venv\Scripts\python.exe monitor.py --symbols MAGICUSDT BTCUSDT ETHUSDT
```

REST initialization only:

```powershell
.\.venv\Scripts\python.exe monitor.py --bootstrap-only
```

`--output PATH` overrides the output directory. The default is `data` beside
the program, independent of the current working directory. Only one process
can write to the same output directory, enforced by `.monitor.lock`.

The `monitor.spotgoods` setting in `Contract.json` enables the spot strategy.
When `spotgoods.symbols` is omitted or empty, the monitor symbol list is reused;
a non-empty list selects spot symbols independently. Symbols without an active
USDT spot market are skipped. Spot collection uses Binance Spot REST and
WebSocket, not the USD-M contract feed.

## Files and event flow

Each symbol has candle and strategy history for every configured interval. The
existing 15m filenames are retained; other intervals use names such as:

```text
data/MAGICUSDT/15k.txt
data/MAGICUSDT/strategy.txt
data/MAGICUSDT/candles_5m.txt
data/MAGICUSDT/strategy_5m.txt
data/MAGICUSDT/candles_1h.txt
data/MAGICUSDT/strategy_1h.txt
data/MAGICUSDT/candles_4h.txt
data/MAGICUSDT/strategy_4h.txt
data/MAGICUSDT/spot_1m.txt
data/MAGICUSDT/spotgoods_strategy.txt
data/BTCUSDT/15k.txt
data/BTCUSDT/strategy.txt
data/signals.txt
data/repeat_signals.txt
```

All files are UTF-8 JSON Lines: one JSON object per line. Candle, strategy, and
signal history is appended, not overwritten. The repeat-signal snapshot is
replaced. Do not manually edit files while the monitor is running.

- Candle files: symbol, interval, UTC Unix millisecond open/close timestamps,
   readable `open_time_tw` / `close_time_tw` in Taiwan time (UTC+8), OHLC price
   strings, `candle: false`, `is_closed: true`, and source. Readable times include
   milliseconds when nonzero. These fields are added to new records only;
   existing history is not rewritten and still loads normally.
- Strategy files: evaluated candle timestamp, pressure lower/upper bounds,
  selected pressure and signal candle timestamps, four condition flags,
  `short_signal`, reason, source, and rules version. Results are recorded even
  when there is no signal; absent pressure bounds are `null`.
- Spot strategy files: one evaluation per newly closed 1m candle after 3 bars
   are available. Each bar must close above its open and have a high strictly
   more than 1% above its open. The shared `signals.txt` receives a spot record
   when this condition first becomes true in a streak; continued qualifying
   candles do not repeatedly append the same streak. Records include
   `strategy_id: "spotgoods"`, `market: "spot"`, `direction: "long"`, interval,
   rule version, source, and evaluated candle time. Spot records do not
   participate in the existing contract `repeat_signals.txt` confirmation.

Here `candle` means **still forming**. Binance `k.x` means **is closed**.
Consequently only `k.x == true` is written as `candle: false`; unfinished
WebSocket updates are ignored. WebSocket streams push frequent updates, but
calculation happens only once per newly recorded closed candle for its interval.

On first startup, Binance server time determines the current boundary for each
interval. REST retrieves exactly the preceding 12 completed candles for every
symbol and interval, records them, then writes an initial strategy result. The
active candles are excluded. Each interval's WebSocket connection synchronizes
again before processing messages, covering candles closed between initialization
and connection.

Each interval connection reconnects with exponential backoff, ping/pong, and
REST recovery. REST recovery is also triggered when a new closed event skips a
candle. Missing bars are written and evaluated in chronological order, with
`source: rest_backfill`.
Duplicates are ignored by opening timestamp. Restarts reload the last 12
recorded candles and backfill gaps rather than writing another copy of the
initial 12. An interrupted calculation is recovered from the candle file.
Non-contiguous or corrupt history stops processing rather than issuing a
misleading signal; inspect the error before restarting.

## Current multi-interval confirmations

`repeat_signals.txt` contains one summary per symbol with live short signals on
at least two different configured intervals. Each symbol/interval contributes
at most once, regardless of historical signal count. Only `source: websocket`
signals count; bootstrap, REST backfill, and recovery remain in historical
outputs with their original sources, but do not count as live confirmations.

Validity uses the local system clock in Unix milliseconds. For each interval,
only the signal whose `evaluated_bar_open_time` equals
`(now_ms // interval_ms - 1) * interval_ms` qualifies. For example, at Taiwan
time 10:37, qualifying bars are 10:30-10:35 (5m), 10:15-10:30 (15m),
09:00-10:00 (1h), and 04:00-08:00 (4h). A missing latest candle never falls
back to an older signal. Keep the system clock synchronized.

All interval workers share a locked aggregator. The snapshot updates after
each evaluation, including non-signals, and refreshes every second while the
WebSocket monitor is running, even without incoming messages. Boundary expiry
can therefore take up to approximately one second to appear on disk. Writes
use a temporary file and atomic replacement; an empty file means no repeated
symbols currently qualify. Startup rebuilds the snapshot from existing history
for the monitored symbols and intervals without appending duplicate signals.
Bootstrap-only mode writes a snapshot but does not keep refreshing after exit.

Each summary includes `symbol`, `direction`, `total_count`,
`distinct_interval_count`, `intervals`, `generated_at`, `expires_at`, and
`signals`. Each signal includes its interval, evaluated candle opening time,
confirmation time (the next candle boundary), expiry time, and original source.
Timestamps are Unix milliseconds, with matching `_tw` readable fields. The
summary expires at its earliest member expiry, when its exact membership may
change. Consumers must reject expired snapshots even if the monitor has stopped.
Confirmation count is not a win-rate estimate or an automatic order instruction.

## Fixed strategy rules (version 1)

For each rolling 12-candle window on each interval:

1. The first 8 candles establish pressure; the last 4 test the signal.
2. Pressure candidates require `close < high`.
3. A group must have `(max_close / min_close) - 1 <= 0.01` and at least 2 bars.
   Choose the largest qualifying group. Ties compare member timestamps sorted
   newest first and choose the lexicographically newest group.
4. Pressure lower/upper are respectively the minimum/maximum member high.
5. The last 4 closes must be: `< lower`, `> upper`, inside `[lower, upper]`,
   then `< lower`. Wick touches do not satisfy the breakout condition.

All price comparisons use `Decimal`. A `short_signal: true` is a candidate
identified after the fourth candle closes, not an order or a profitability
claim. Backfilled results are historical, not live entry instructions. Stops,
position sizing, exits, open interest filters, and backtesting are not included.
This implementation calculates resistance, not a separate support zone.

## Offline tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p test_strategy.py -v
```

Tests cover rule boundaries, all four signal conditions, interval-specific
continuity and REST bootstrap, independent per-interval state, shared interval-
tagged signals, the disjoint 8+4 window, closed-only handling, deduplication,
restart and gap recovery, multi-symbol isolation, bootstrap exclusion of active
bars, spot 1m strict-threshold evaluation and signal deduplication, and Ctrl+C.