# Binance 多週期策略監控器

記錄公開的 USD-M USDT 永續合約 K 線，供失敗突破做空策略使用；同時記錄 Binance 現貨 K 線，供 `spotgoods` 做多策略使用。此程式不需要 API 金鑰或帳戶存取權，也不會送出委託。需要 Python 3.10 或更新版本，以及網路連線至 Binance。

## 設定與執行

在此目錄中，使用已安裝的 Python 直譯器執行以下命令：

```powershell
python -m venv .venv
\.venv\Scripts\python.exe -m pip install -r requirements.txt
\.venv\Scripts\python.exe monitor.py
```

監控器會持續執行，直到按下 Ctrl+C 停止。若要在 Windows PowerShell 中另外啟動背景處理程序：

```powershell
$process = Start-Process -FilePath "$PWD\.venv\Scripts\python.exe" -ArgumentList 'monitor.py' -WorkingDirectory $PWD -PassThru
$process.Id
```

建議在互動式終端機中按 Ctrl+C，以正常停止程式。若要無人值守執行，請在 Windows 工作排程器中設定此目錄為工作目錄。若在寫入檔案期間強制終止，可能會留下不完整的 JSON 行。

設定的週期為 `5m`、`15m`、`1h` 和 `4h`。每個週期使用一條合併的 WebSocket 連線，並為每個交易對及週期維護獨立狀態：

```powershell
\.venv\Scripts\python.exe monitor.py --symbols MAGICUSDT BTCUSDT ETHUSDT
```

僅執行 REST 初始化：

```powershell
\.venv\Scripts\python.exe monitor.py --bootstrap-only
```

`--output PATH` 可指定輸出目錄。預設目錄為程式所在位置旁的 `data`，不受目前工作目錄影響。同一個輸出目錄只允許一個程序寫入，並透過 `.monitor.lock` 強制限制。

`Contract.json` 中的 `monitor.spotgoods` 設定可啟用現貨策略。若未提供 `spotgoods.symbols` 或清單為空，監控器會沿用監控交易對清單；若清單非空，則會獨立指定現貨交易對。沒有有效 USDT 現貨市場的交易對會略過。現貨資料透過 Binance Spot REST 和 WebSocket 收集，不會使用 USD-M 合約資料流。

## 檔案與事件流程

每個交易對的每個設定週期，都會有 K 線與策略歷史資料。既有的 15m 檔名會保留；其他週期使用類似以下的檔名：

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

所有檔案皆為 UTF-8 JSON Lines 格式，每行一個 JSON 物件。K 線、策略和訊號歷史資料採附加寫入，不會覆寫；重複訊號快照則會取代舊資料。監控器執行期間請勿手動編輯這些檔案。

- K 線檔案：包含交易對、週期、UTC Unix 毫秒格式的開盤／收盤時間戳記、臺灣時間（UTC+8）的易讀欄位 `open_time_tw`／`close_time_tw`、OHLC 價格字串、`candle: false`、`is_closed: true` 及來源。易讀時間在毫秒不為零時會包含毫秒。這些欄位只會新增至新記錄；既有歷史資料不會重寫，仍可正常載入。
- 策略檔案：包含評估 K 線時間戳記、壓力區間下限／上限、選定壓力區與訊號 K 線的時間戳記、四個條件旗標、`short_signal`、原因、來源及規則版本。即使沒有訊號也會記錄結果；不存在的壓力區間界限會以 `null` 表示。
- 現貨策略檔案：每根新收盤的 1m K 線最多評估一次，且至少要有 3 根 K 線。每根 K 線都必須收盤價高於開盤價，且最高價嚴格高於開盤價 1% 以上。此條件在連續走勢中首次成立時，共用的 `signals.txt` 會新增一筆現貨記錄；之後連續符合條件的 K 線不會對同一段走勢重複新增記錄。記錄包含 `strategy_id: "spotgoods"`、`market: "spot"`、`direction: "long"`、週期、規則版本、來源及評估 K 線時間。現貨記錄不會參與既有合約 `repeat_signals.txt` 的確認。

此處的 `candle` 表示**仍在形成中**；Binance 的 `k.x` 表示**已收盤**。因此，只有 `k.x == true` 的 K 線才會以 `candle: false` 寫入；尚未完成的 WebSocket 更新會忽略。WebSocket 資料流會頻繁推送更新，但每個週期只會在新收盤 K 線記錄一次後進行計算。

首次啟動時，程式會依 Binance 伺服器時間判定各週期目前的時間邊界。REST 會為每個交易對及週期恰好取得前 12 根已收盤 K 線、記錄資料，然後寫入初始策略結果。進行中的 K 線不會納入。每個週期的 WebSocket 連線在處理訊息前會再次同步，以涵蓋初始化與連線完成之間收盤的 K 線。

每個週期的連線都會以指數退避方式重新連線，並使用 ping/pong 與 REST 復原機制。若新收盤事件中間有跳過 K 線，也會觸發 REST 復原。缺漏的 K 線會依時間順序寫入並評估，來源為 `source: rest_backfill`。

程式會依開盤時間戳記忽略重複資料。重新啟動時會載入最近 12 根已記錄 K 線並補回缺漏，不會再次寫入初始的 12 根。若計算中斷，程式會從 K 線檔案復原。若歷史資料不連續或已損毀，處理程序會停止，以免產生誤導訊號；重新啟動前請先檢查錯誤。

## 目前的多週期確認訊號

`repeat_signals.txt` 會針對至少有兩個不同設定週期出現有效做空訊號的交易對，各產生一筆摘要。每個交易對的每個週期最多計入一次，不受歷史訊號數量影響。只有 `source: websocket` 的訊號會計入；bootstrap、REST 補漏和復原結果仍會以原始來源保留在歷史輸出中，但不會計入即時確認。

有效性依本機系統時鐘的 Unix 毫秒計算。對每個週期，只有 `evaluated_bar_open_time` 等於 `(now_ms // interval_ms - 1) * interval_ms` 的訊號才符合資格。例如，臺灣時間 10:37 時，符合資格的 K 線為 10:30-10:35（5m）、10:15-10:30（15m）、09:00-10:00（1h）和 04:00-08:00（4h）。若最新 K 線不存在，不會退回使用較舊訊號。請保持系統時鐘同步。

所有週期工作程序共用一個具鎖定機制的彙總器。每次評估後都會更新快照，包括沒有訊號的情況；WebSocket 監控執行期間，即使沒有收到訊息，也會每秒重新整理。因邊界到期而移除訊號，可能最多約一秒後才反映在磁碟上。寫入時會先建立暫存檔，再以原子方式取代；空檔表示目前沒有符合條件的重複交易對。啟動時會根據正在監控的交易對與週期，從既有歷史資料重建快照，不會附加重複訊號。僅初始化模式會寫入快照，但結束後不會持續更新。

每筆摘要包含 `symbol`、`direction`、`total_count`、`distinct_interval_count`、`intervals`、`generated_at`、`expires_at` 和 `signals`。每筆訊號包含週期、評估 K 線開盤時間、確認時間（下一根 K 線的邊界）、到期時間及原始來源。時間戳記為 Unix 毫秒，並附有對應的易讀欄位 `_tw`。摘要會在其中最早到期的訊號到期時失效，此時摘要成員可能改變。即使監控器已停止，讀取端也必須拒絕已過期的快照。確認訊號數量不代表勝率估計，也不是自動下單指示。

## 固定策略規則（版本 1）

對每個週期的每個連續 12 根 K 線視窗：

1. 前 8 根 K 線用來建立壓力區；後 4 根用來檢查訊號。
2. 壓力候選 K 線必須符合 `close < high`。
3. 群組必須符合 `(max_close / min_close) - 1 <= 0.01` 且至少包含 2 根 K 線。選擇符合條件且最大的群組。若大小相同，將成員時間戳記由新到舊排序後比較，選擇字典序最新的群組。
4. 壓力區下限／上限分別為群組成員最高價的最小值／最大值。
5. 後 4 根 K 線的收盤價必須依序為：`< lower`、`> upper`、位於 `[lower, upper]` 內，接著 `< lower`。僅影線觸及不符合突破條件。

所有價格比較皆使用 `Decimal`。`short_signal: true` 表示第四根 K 線收盤後識別出的候選訊號，不代表委託或獲利承諾。補回的結果屬於歷史資料，不是即時進場指示。此處未包含停損、部位規模、出場、未平倉量篩選或回測。本實作計算的是阻力區，不會另行計算支撐區。

## 離線測試

```powershell
\.venv\Scripts\python.exe -m unittest discover -s . -p test_strategy.py -v
```

測試涵蓋規則邊界、四個訊號條件、各週期獨立的連續性與 REST 初始化、每個週期獨立狀態、共用且標記週期的訊號、互不重疊的 8+4 根 K 線視窗、僅處理已收盤 K 線、去重、重新啟動與缺漏復原、多交易對隔離、初始化時排除進行中的 K 線、現貨 1m 嚴格門檻評估與訊號去重，以及 Ctrl+C 停止處理。