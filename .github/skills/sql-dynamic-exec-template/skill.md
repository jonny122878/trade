---
name: sql-dynamic-exec-template
description: "當你要我幫忙整理這類 SQL 時可以用這個：像是依 EXEC_MERCHANT_NO、EXEC_CPT_DATE 組動態 SQL、算月份區間、改清分或匯出報表、把查詢包成 @SQL_String、判斷是否要拆成多段動態 SQL，或參考 split.sql 整理輸出欄位。"
argument-hint: "貼上 SQL、說明你要查哪張表、日期怎麼算，或直接說你想改成什麼報表格式"
---

# SQL 動態參數腳本草稿規範

## 適用情境

當 SQL 腳本具有下列特徵時，使用此 skill：

- 以 `EXEC_MERCHANT_NO` 作為機構、票種或商家識別參數
- 以 `EXEC_CPT_DATE` 作為執行日期或會計日期參數
- 主要查詢邏輯需要組成動態字串 `@SQL_String`
- 日期區間需由 `EXEC_CPT_DATE` 推導出當月、前月或指定結帳區間
- 查詢結果是匯出、清分、結算、退票金額或報表類資料

---

## 目標

- 統一這類 SQL 的參數命名與區間計算方式
- 維持輸出欄位與彙總邏輯的一致性
- 降低動態 SQL 拼字錯誤、引號錯誤與日期範圍錯誤
- 讓同類腳本容易複製、審查與維護

---

## 標準參數

預設使用以下參數：

- `@EXEC_MERCHANT_NO`：月票名稱、商家名稱或業務代碼
- `@EXEC_CPT_DATE`：執行日期，型別建議為 `DATE`

若原始檔案使用其他參數名，優先對齊既有專案慣例，但應保持語意一致。

---

## 標準日期區間規則

若需求是「以前一個月」為查詢區間，建議使用下列模式：

```sql
DECLARE @DATE_FROM VARCHAR(8) = CONVERT(VARCHAR(6), DATEADD(M, -1, @EXEC_CPT_DATE), 112) + '01'
DECLARE @DATE_TO   VARCHAR(8) = CONVERT(VARCHAR(8), DATEADD(D, -1, DATEADD(M, 1, @DATE_FROM)), 112)
```

### 檢查重點

- `@EXEC_CPT_DATE` 是否有被正確宣告與傳入
- `@DATE_FROM` 是否真的是前一個月月初
- `@DATE_TO` 是否真的是前一個月月底
- `CPT_DATE` 欄位型別是否與字串區間比較相容

---

## 動態 SQL 標準結構

建議將查詢主體放在 `@SQL_String`，但保持結構一致：

1. 先宣告參數與日期區間
2. 再組裝 SQL 字串
3. 用固定的 `SELECT`、`FROM`、`WHERE`、`GROUP BY` 區塊撰寫主邏輯
4. 最後執行動態 SQL

### 建議格式

```sql
DECLARE @SQL_String NVARCHAR(MAX)

SET @SQL_String = '
SELECT ...
FROM ...
WHERE CPT_DATE BETWEEN ''' + @DATE_FROM + ''' AND ''' + @DATE_TO + '''
  AND MONTHLY_PASS_NAME = ''' + @EXEC_MERCHANT_NO + ''''

EXEC (@SQL_String)
```

---

## 是否拆分的判斷規則

此 skill 需要先判斷動態 SQL 應維持單段，還是拆成多段字串後再組合執行。

### 預設原則

- 若查詢邏輯單純、段落短、只有一段主查詢，優先維持單一 `@SQL_String`
- 若查詢邏輯已明顯偏長、包含多個區塊，優先拆成多段字串
- 若使用者明確要求參考既有拆分格式，直接採拆分版本，不再保留單段

### 優先維持單段的情況

- 只有一段主要 `SELECT ... FROM ... WHERE ...` 查詢
- 只有單一彙總段，且沒有額外暫存表建立流程
- 查詢大致仍可在同一段字串中清楚閱讀與維護
- 使用者明確要求不要拆分

### 優先拆分的情況

- 主體大約超過 80 到 120 行，或已明顯影響可讀性
- 同時包含明細段與統計彙總段，例如明細 `SELECT` 再加 `UNION ALL` 彙總
- 包含多個暫存表、前置資料準備段、查詢主體段、收尾段
- 有兩層以上巢狀子查詢，且欄位與 `CASE WHEN` 明顯偏多
- 需要 `DROP TABLE`、排序收尾、補資料列或額外插入資料表變數等尾段處理
- 使用者要求參考既有拆分檔案風格
- 參考範例已採分段拼接模式

### 無法確定時的處理

- 不需要先到 MS-SQL 執行才決定
- 以可讀性與維護成本作為第一判斷依據
- 若 SQL 看起來接近臨界值，優先拆分，不要等執行失敗才重構
- 除非使用者要求保守維持原樣，否則對中大型報表 SQL 可偏向拆分

---

## 拆分格式規則

當判斷結果需要拆分時，請參考 `split.sql` 的方式，不要任意切碎。

### 拆分目標

- 讓每段字串各自承擔明確責任
- 降低單引號跳脫與維護成本
- 讓前置段、主查詢段、彙總段、收尾段可分開閱讀與比對

### 建議拆分方式

- 前置查詢或條件準備段：例如 `@SQL_String_TARGET_STORE`
- 主查詢段：例如 `@SQL_String`
- 若主查詢仍過長，可再拆成 `@SQL_String_HEAD`、`@SQL_String_BODY`、`@SQL_String_SUMMARY`、`@SQL_String_TAIL`
- 最後以字串相加後 `EXEC (...)`

### 拆分原則

- 每段依功能切分，不要只是平均切行數
- `DECLARE`、前置資料整理、`INTO #TEMP`、主查詢、彙總、排序、清除暫存表，盡量分屬不同段
- 若某段會被條件式切換，例如不同商家使用不同前置查詢，可獨立成一個變數
- 主查詢欄位清單與彙總欄位清單若很長，可拆成主體段與統計段，但應保持欄位對齊

### 執行格式

```sql
DECLARE @SQL_String_1 NVARCHAR(MAX)
DECLARE @SQL_String_2 NVARCHAR(MAX)

SET @SQL_String_1 = '...'
SET @SQL_String_2 = '...'

EXEC (@SQL_String_1 + @SQL_String_2)
```

若已有更具語意的名稱，優先使用語意化命名，不必強制使用流水號。

---

## 撰寫原則

- 簡單查詢可集中在同一段 `SET @SQL_String`；複雜查詢則依判斷規則拆段。
- 固定欄位別名要語意化，例如 `退票金額`、`清分服務費`、`預備金`、`匯費`、`調整數`。
- 加總欄位若可能為 `NULL`，應評估是否要用 `ISNULL(..., 0)`。
- 比照既有報表腳本格式，簡單情況維持 `SET @SQL_String = ...` 後搭配 `EXEC (@SQL_String)`；複雜情況則比照 `split.sql` 拆段。
- 若查詢涉及多個金額欄位，總計公式要與欄位別名一致，避免漏算或重複計算。
- 不要為了拆分而拆分；拆分後必須比單段更容易閱讀與修改。

---

## 安全與維護檢查

在產出或整理這類 SQL 時，必須檢查：

- 是否有 SQL injection 風險
- 是否有硬編碼日期、名稱或環境值
- `EXEC_CPT_DATE` 是否被當成字串亂轉型
- 動態 SQL 中的單引號是否正確成對
- `EXEC` 是否能改成更安全、可維護的執行方式
- 查詢欄位與來源表名稱是否清楚，方便後續追查

---

## 產出要求

回覆時應優先提供下列其中一種結果：

- 將現有 SQL 整理成一致格式的版本
- 補齊缺漏參數與日期區間邏輯
- 說明這支 SQL 的用途、來源表與彙總欄位
- 指出風險點與建議修正

## 相關範本

- [template.sql](template.sql)：可直接套用的參數化查詢範例
- [split.sql](split.sql)：動態 SQL 過長時可參考的拆分範例

---

## 不適用情境

以下情況不建議使用此 skill：

- 只是做單次查詢，不需要共用模板
- SQL 不是以動態字串方式組裝
- 查詢邏輯與 `EXEC_MERCHANT_NO`、`EXEC_CPT_DATE` 無關
- 需求是完整重構成 stored procedure、function 或報表程式
