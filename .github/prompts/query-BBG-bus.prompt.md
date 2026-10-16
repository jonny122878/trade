查詢客運對照（BBG）

目的
- 當使用者輸入客運名稱或 MERCHANT_NO 時，先在本專案的對照檔中找對應資料；若未命中，回傳可直接使用的 SQL 查詢模板供後續查詢。

流程
1) 先判斷使用者輸入類型：
- 若為 8 碼純數字（例如 35025506），走「編號查詢模式」。
- 若為中文名稱或含中文內容（例如 三重客運、首都客運），走「名稱查詢模式」。
- 若既不是 8 碼純數字，也不是中文，則走「結構查詢模式（MERCH_SCHEMAID）」。

2) 編號查詢模式
- 在 schema/docs/BBG客運路線對照.md 中，以完整比對方式搜尋 MERCHANT_NO 欄位。
- 若找到一或多筆，回傳所有命中列，每筆包含 MERCH_SCHEMAID、MERCHANT_NAME。
- 若未找到，回傳下列 SQL 模板，並把 {MERCHANT_NO} 替換為使用者原始輸入：

```
SELECT TOP 10 * FROM dbo.GM_MERCHANT WHERE MERCHANT_NO = '{MERCHANT_NO}'
```

3) 名稱查詢模式
- 在 schema/docs/BBG客運路線對照.md 中，以不分大小寫的「包含」方式搜尋 MERCHANT_NAME 與「別名」欄位。
- 若找到一或多筆，回傳所有命中列，每筆包含 MERCHANT_NO、MERCHANT_NAME、MERCH_SCHEMAID。
- 若未找到，回傳下列 SQL 模板，並把 {MERCHANT_NAME} 替換為使用者原始輸入：

```
SELECT TOP 10 * FROM dbo.GM_MERCHANT WHERE MERCHANT_NAME like '%{MERCHANT_NAME}%'
```

4) 結構查詢模式（MERCH_SCHEMAID）
- 在 schema/docs/BBG客運路線對照.md 中，以完整比對方式搜尋 MERCH_SCHEMAID 欄位。
- 若找到一或多筆，回傳所有命中列，每筆包含 MERCHANT_NO、MERCHANT_NAME、MERCH_SCHEMAID。
- 若未找到，回傳下列 SQL 模板，並把 {MERCH_SCHEMAID} 替換為使用者原始輸入：

```
SELECT TOP 10 * FROM dbo.GM_MERCHANT WHERE MERCH_SCHEMAID = '{MERCH_SCHEMAID}'
```

比對細節
- MERCHANT_NO：完整比對（exact match）。
- MERCHANT_NAME 與別名：不分大小寫、部分字串匹配（contains）。
- MERCH_SCHEMAID：完整比對（exact match），適用於 B101、B108、TYB、RYA 等結構代碼。
- 若檔內多筆符合，全部列出，順序維持檔案中出現的順序。

回傳格式（範例）
- 編號命中（單筆或多筆）：
  - JSON（簡潔）或純文字清單，例如：
    [{"MERCH_SCHEMAID":"B112","MERCHANT_NAME":"三重汽車客運"}]
  - 或純文字：MERCH_SCHEMAID: B112, MERCHANT_NAME: 三重汽車客運
- 編號未命中：回傳 SQL 模板且替換 {MERCHANT_NO}，例如：
  - SELECT TOP 10 * FROM dbo.GM_MERCHANT WHERE MERCHANT_NO = '99999999'
- 名稱命中（單筆或多筆）：
  - JSON（簡潔）或純文字清單，例如：
    [{"MERCHANT_NO":"35025506","MERCHANT_NAME":"三重汽車客運","MERCH_SCHEMAID":"B112"}]
  - 或純文字：MERCHANT_NO: 35025506, MERCHANT_NAME: 三重汽車客運, MERCH_SCHEMAID: B112
- 名稱未命中：回傳 SQL 模板且替換 {MERCHANT_NAME}，例如：
  - SELECT TOP 10 * FROM dbo.GM_MERCHANT WHERE MERCHANT_NAME like '%某不存在公司%'
- 結構命中（單筆或多筆）：
  - JSON（簡潔）或純文字清單，例如：
    [{"MERCHANT_NO":"27043501","MERCHANT_NAME":"指南汽車客運","MERCH_SCHEMAID":"B108"}]
  - 或純文字：MERCHANT_NO: 27043501, MERCHANT_NAME: 指南汽車客運, MERCH_SCHEMAID: B108
- 結構未命中：回傳 SQL 模板且替換 {MERCH_SCHEMAID}，例如：
  - SELECT TOP 10 * FROM dbo.GM_MERCHANT WHERE MERCH_SCHEMAID = 'B999'

範例對話
- 使用者: 35025506
- 助手（命中）: {"MERCH_SCHEMAID":"B112","MERCHANT_NAME":"三重汽車客運"}

- 使用者: 99999999
- 助手（未命中）: SELECT TOP 10 * FROM dbo.GM_MERCHANT WHERE MERCHANT_NO = '99999999'

- 使用者: 三重客運
- 助手（命中）: {"MERCHANT_NO":"35025506","MERCHANT_NAME":"三重汽車客運","MERCH_SCHEMAID":"B112"}

- 使用者: 假想客運公司
- 助手（未命中）: SELECT TOP 10 * FROM dbo.GM_MERCHANT WHERE MERCHANT_NAME like '%假想客運公司%'

- 使用者: B108
- 助手（命中）: {"MERCHANT_NO":"27043501","MERCHANT_NAME":"指南汽車客運","MERCH_SCHEMAID":"B108"}

- 使用者: B999
- 助手（未命中）: SELECT TOP 10 * FROM dbo.GM_MERCHANT WHERE MERCH_SCHEMAID = 'B999'

注意事項
- 優先直接讀取 schema/docs/BBG客運路線對照.md，不要依賴外部網路或資料庫。若使用者要求，也可以同時提供建議的下一步（例如貼上 SQL 到資料庫工具執行）。

維護建議
- 若要新增或更新對照，直接編輯 schema/docs/BBG客運路線對照.md。
