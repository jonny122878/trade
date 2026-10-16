# EXPORT_MONTHLY_PASS

簡介
--
此 skill 提供 `EXPORT_MONTHLY_PASS` 的說明與範本（template），方便外部系統或手動呼叫以動態參數執行 SQL。

目標
--
- 管理與共用參數化 SQL 範本
- 說明必要參數與建議的執行方式

參數
--
- `EXEC_CPT_DATE` (char(8))：對應原 SQL 的 `WRITE_OFF_START_DATE`，格式例如 `20260501`。
- `EXEC_MERCHANT_NO` (nvarchar(200))：對應原 SQL 的 `MONTHLY_PASS_NAME`，例如 `基隆區月票`。

使用說明
--
1. 取得範本檔案：`.github/skills/EXPORT_MONTHLY_PASS/template.sql`
2. 用 `sp_executesql` 或外部程式（如 PowerShell / Python）傳入 `EXEC_CPT_DATE` 與 `EXEC_MERCHANT_NO` 執行。

範例（在 SQL Server 中使用 sp_executesql）
--
請參考 template.sql 內的範例片段。

備註
--
- 這個 skill 只包含說明與範本；若需要一鍵執行請要求新增 `script` 或 `stored procedure`。
