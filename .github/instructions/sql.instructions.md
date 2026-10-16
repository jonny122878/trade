---
applyTo: "**/*.sql"
---

- 回答與程式碼註解一律使用繁體中文。
- 修改任何 SQL 檔前，先檢查檔案開頭是否已宣告 `@EXEC_CPT_DATE` 與 `@EXEC_MERCHANT_NO`。
- 若任一宣告缺少，必須在檔案最開頭補上以下完整區塊；不得將兩個 `DECLARE` 註解掉：

  ```sql
  -- 執行參數：結算日期，格式 YYYYMMDD。
  --DECLARE @EXEC_CPT_DATE VARCHAR(8) = '20260701'
  -- 執行參數：特店／業者編號。
  --DECLARE @EXEC_MERCHANT_NO VARCHAR(20) = '51817006'
  ```

- 若兩個宣告已存在但缺少用途備註，須在各自的 `DECLARE` 前補上對應備註。
- 完成修改後，再確認這兩個可執行的 `DECLARE` 位於檔案開頭，且弄成註解。
