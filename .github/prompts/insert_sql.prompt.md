# 生成 INSERT SQL
參數1：參考資料表結構
參數2：要 insert data 的 CSV

請根據參數1 判斷資料表名稱、欄位順序、資料型別與主鍵資訊，並根據參數2 將 CSV 轉成可直接執行的 SQL `INSERT` 腳本。

輸出規則：
- 參考範例檔案格式：AM_ISET_MERC_TRANS_LOG_D_INSERT.sql
- 先輸出 `USE [iSettle2]` 與 `GO`
- 以 `BEGIN TRY / BEGIN CATCH` 包住整段交易
- 交易內先執行 `BEGIN TRAN`
- 在 `INSERT` 前加入：`DELETE FROM AM_ISET_MERC_TRANS_LOG_D WHERE CPT_DATE BETWEEN '20260601' AND '20260630';`
- `DELETE` 與 `INSERT` 必須在同一個交易內
- 失敗時要 `ROLLBACK TRAN`
- 成功時要 `COMMIT TRAN`
- 必要時加入 `SET XACT_ABORT ON`
- 只輸出 SQL，不要額外說明

輸出格式範例：
```sql
USE [iSettle2]
GO

SET XACT_ABORT ON;

BEGIN TRY
BEGIN TRAN;

DELETE FROM AM_ISET_MERC_TRANS_LOG_D
WHERE CPT_DATE BETWEEN '20260601' AND '20260630';

INSERT INTO [dbo].[AM_ISET_MERC_TRANS_LOG_D] (...) 
VALUES
(...);

COMMIT TRAN;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRAN;
    THROW;
END CATCH
GO
```
