# Binance 15m failed-breakout monitor

Records public USD-M USDT perpetual contract candles and short-signal candidates.
Default symbol: `MAGICUSDT`. No API key, account access, or order submission.
Requires Python 3.10 or newer and network access to Binance.

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

Multiple symbols use one combined WebSocket with independent per-symbol state:

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

## Files and event flow

Each symbol has exactly two history files, for example:

```text
data/MAGICUSDT/15k.txt
data/MAGICUSDT/strategy.txt
data/BTCUSDT/15k.txt
data/BTCUSDT/strategy.txt
```

Both files are UTF-8 JSON Lines: one JSON object per line. History is appended,
not overwritten. Do not manually edit files while the monitor is running.

- `15k.txt`: symbol, interval, UTC Unix millisecond open/close timestamps,
   readable `open_time_tw` / `close_time_tw` in Taiwan time (UTC+8), OHLC price
   strings, `candle: false`, `is_closed: true`, and source. Readable times include
   milliseconds when nonzero. These fields are added to new records only;
   existing history is not rewritten and still loads normally.
- `strategy.txt`: evaluated candle timestamp, pressure lower/upper bounds,
  selected pressure and signal candle timestamps, four condition flags,
  `short_signal`, reason, source, and rules version. Results are recorded even
  when there is no signal; absent pressure bounds are `null`.

Here `candle` means **still forming**. Binance `k.x` means **is closed**.
Consequently only `k.x == true` is written as `candle: false`; unfinished
WebSocket updates are ignored. WebSocket streams push frequent updates, but
calculation happens only once per newly recorded closed 15m candle.

On first startup, Binance server time determines the current UTC 15m boundary.
REST retrieves exactly the preceding 12 completed candles, records all 12,
then writes one initial strategy result. The active candle is excluded.
The stream connects and REST synchronization runs again before processing
messages, covering candles closed between initialization and connection.

Reconnects use exponential backoff, ping/pong, and REST recovery. REST recovery
is also triggered when a new closed event skips a candle. Missing bars are
written and evaluated in chronological order, with `source: rest_backfill`.
Duplicates are ignored by opening timestamp. Restarts reload the last 12
recorded candles and backfill gaps rather than writing another copy of the
initial 12. An interrupted calculation is recovered from the candle file.
Non-contiguous or corrupt history stops processing rather than issuing a
misleading signal; inspect the error before restarting.

## Fixed strategy rules (version 1)

For each rolling 12-candle window:

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

Tests cover rule boundaries, all four signal conditions, the disjoint 8+4
window, closed-only handling, deduplication, restart recovery, gap recovery,
multi-symbol isolation, bootstrap exclusion of active bars, and Ctrl+C.