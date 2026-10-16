# Binance Monitoring Tag 爬取計畫

## 目標

建立獨立、手動執行的程式，檢查 `Contract.json` 中 `monitor.symbols` 對應的幣種是否有 Binance Spot Monitoring Tag，並輸出可追溯的 JSON 報告。

第一版只檢查並回報結果，不修改 `Contract.json`、不改變 `monitor.py` 的訂閱清單，也不自動排程。

## 現況與資料來源

- `Contract.json` 的 `monitor.symbols` 是目前 USD-M Futures 監控清單。
- `crawl_contract.py` 已取得 Spot 與 Futures 的 `exchangeInfo`，但公開欄位沒有 Monitoring Tag，因此不能用合約 `status` 推斷標籤。
- Monitoring Tag 顯示於 Binance Spot 交易頁。實作前需透過瀏覽器開發者工具確認頁面載入標籤時實際使用的 Network JSON 請求與回應欄位。
- 優先使用頁面呼叫的結構化 JSON 資料；此端點若非公開文件化 API，需視為可能變更的資料來源並加入欄位驗證。若沒有可用的 JSON 資料，再評估透過瀏覽器擷取 DOM 標籤。
- 不可在資料來源失敗或欄位缺漏時，將所有幣種判為「未標記」。

## 實作步驟

1. **確認標籤資料**
	- 分別查看一個當下確定有 Monitoring Tag 及一個沒有標籤的 Spot 頁面。
	- 記錄 Network 請求 URL、必要參數、回應結構、標籤欄位及回應涵蓋範圍。
	- 確認標籤是資產層級還是交易對層級，以及可用的識別欄位。
	- `MOVR/USDT` 可作候選正向樣本，但需在實作當下重新確認標籤狀態。

2. **新增獨立掃描器**
	- 新增 `crawl_monitoring_tag.py`，讀取 `Contract.json` 的 `monitor.symbols`。
	- 優先使用 `contract_symbols.json` 中 `contracts[].baseAsset` 對應資產，避免把 `1000...USDT` 等合約 symbol 直接當成 Spot 資產名稱。
	- 若資料來源提供完整標籤清單，應一次取得後批次比對，不要逐一開啟數百個交易頁。
	- 若來源只能逐頁查詢，需限制併發、加入請求間隔、逾時及有限重試；不可高頻請求。
	- 參考 `crawl_contract.py` 現有的標準庫 HTTP、錯誤處理與原子寫檔方式，先避免不必要的新依賴。

3. **輸出報告**
	- 建議輸出為 `monitoring_tag_report.json`，包含查詢 UTC 時間、來源 URL、每個 Futures symbol、對應的 base asset、結果狀態及錯誤原因。
	- 狀態至少區分 `tagged`、`untagged`、`unknown`、`error`；僅在來源成功且資料完整時，才能判定為 `untagged`。
	- 同時輸出有標籤的 symbol 摘要及數量，方便人工查看。
	- 使用暫存檔再原子替換正式報告，避免程式中斷留下不完整 JSON。

4. **CLI 與文件**
	- 以獨立手動指令執行，不併入 `crawl_contract.py`，避免標籤來源故障阻斷合約清單更新。
	- 成功時印出檢查數量、有標籤數量及 tagged symbols；來源或解析失敗時回傳非零結束碼。
	- 實作完成後，將本文件補成實際執行方式、報告範例、資料來源及維護注意事項。

5. **測試**
	- 新增 mock-based 測試，不依賴即時 Binance 網路。
	- 覆蓋完整標籤清單比對、Spot/Futures 資產映射、`1000` 前綴合約、來源錯誤、欄位缺漏、unknown 狀態及報告寫入。
	- 確認來源錯誤不會被誤報為全部未標記。

## 預計檔案

- 新增 `crawl_monitoring_tag.py`：掃描與產生報告。
- 新增 `test_crawl_monitoring_tag.py`：離線測試。
- 使用 `Contract.json`：只讀取 `monitor.symbols`，不可由此流程改寫。
- 使用 `contract_symbols.json`：讀取 `baseAsset` 對應資料；缺少映射時回報 `unknown`，不可自行猜測。
- 參考 `crawl_contract.py`：沿用現有 HTTP 與原子 JSON 寫檔慣例，不改變其合約更新行為。

## 驗收條件

1. Mock 測試可正確區分 `tagged`、`untagged`、`unknown` 與 `error`。
2. 使用一個已確認有標籤及一個無標籤的 Spot 資產進行手動 smoke test，結果與頁面顯示一致。
3. 執行前後 `Contract.json` 的 `monitor.symbols` 完全相同。
4. 當資料來源不可用、格式改變或資產無法對應時，程式明確回報錯誤或未知，不輸出錯誤的「未標記」結論。
5. 完整清單掃描時請求數量與執行時間合理，且不對 Binance 造成高頻請求。

## 限制與風險

- 網頁內部 JSON 端點不是穩定的官方 API，可能改版、變更回應欄位或增加存取限制；需保留 schema 驗證及明確錯誤訊息。
- DOM 擷取會受頁面版型、前端載入時間、語系與地區影響；若採用，需驗證頁面確實載入完成且標籤元素存在。
- Monitoring Tag 可能屬於資產而非交易對。確認層級及映射鍵之前，不可假設 Futures symbol 與 Spot pair 一對一相同。
- Spot Monitoring Tag 不等於 Futures 合約不可交易，不可據此自動停用或移除 Futures WebSocket 訂閱。

## 不在第一版範圍

- 自動從 `monitor.symbols` 移除或停用有 Monitoring Tag 的交易對。
- 修改交易策略、K 線 WebSocket、下單流程或 Futures 合約篩選規則。
- 將掃描器併入合約更新流程或設定背景排程。
