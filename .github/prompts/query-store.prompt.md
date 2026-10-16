# 查詢路線建檔（BM_STORE_M）

目的
- 當使用者詢問某客運業者的路線是否已建檔時，將問題轉換為該業者結構下的 `BM_STORE_M` 查詢 SQL。

流程
1) 解析業者
- 從使用者輸入辨識客運名稱、MERCHANT_NO、MERCH_SCHEMAID 或別名。
- 依 query-bus.prompt.md 的規則查詢，取得唯一的 MERCH_SCHEMAID。
- 若有多筆業者命中，回傳所有候選業者並要求使用者指定，不產生 SQL。
- 若沒有業者命中，回傳 query-bus.prompt.md 對應的查詢結果，不產生 BM_STORE_M SQL。

2) 解析路線代碼
- 從使用者輸入中的「路線」附近擷取純數字路線代碼，例如「路線9908」或「9908路線」取得 `9908`。
- 路線代碼只能為 1 至 6 碼數字；超過 6 碼或未提供路線代碼時，回覆原因，不產生 SQL。
- 將路線代碼左補 `0` 至固定 6 碼：`101` -> `000101`、`9908` -> `009908`、`123456` -> `123456`。

3) 產生預設查詢
- 成功取得唯一 MERCH_SCHEMAID 與六碼 STORE_NO 時，只輸出下列 SQL，不加說明：

```sql
SELECT * FROM [{MERCH_SCHEMAID}].BM_STORE_M WHERE STORE_NO IN ('{STORE_NO_6}')
```

4) 指定欄位或條件
- 使用者要求顯示特定資訊時，參考 schema/docs/BM_STORE_M路線對照.md 的欄位定義，將 `SELECT *` 改為所需欄位投射。
- 可用欄位包括 `STORE_NO`、`MERCHANT_NO`、`STO_NAME_SHORT`、`STO_NAME_LONG`、`LINE_QTY`、`OPERATE_TYPE`、`LINE_TYPE`、`CITY_TYPE`、`TRANSFER_TYPE`、`LINE_NO_03`、`SUBSIDY_TYPE`、`LINE_NO_04`、`LINE_SI_NO`。
- 使用者明確要求限定「新北」時，以 `LINE_TYPE = '02'` 作為額外條件；未指定投射欄位時仍使用 `SELECT *`。

5) 附帶剔退查詢
- 每次成功產生第 3) 步的 BM_STORE_M SQL 後，額外參考 查問題/剔退建檔路線.sql，依序附上「查詢剔退明細」與「查詢路線剔退建檔」兩段 SQL。
- 兩段 SQL 皆套用同一組 `{MERCH_SCHEMAID}` 與 `{STORE_NO_6}`；`BM_DIFF_M` 固定引用 `[B116]`，不隨業者替換。
- 日期區間：使用者提問中若有指定日期（含區間或單一日期），套用該範圍；若未指定，預設為當月整月，即 `{目前年月}01` 至 `{目前年月}當月最後一日`（依目前日期換算，例如 2026-09-02 時為 `20260901` ~ `20260930`）。

```sql
-- 查詢剔退明細
SELECT 
D.STORE_NO As 未清分路線代碼,
D.DIFF_FLG As 剔退代碼,
R.DIFF_DESC As 剔退原因
FROM [{MERCH_SCHEMAID}].TM_SKIP_TMLOG_D D
LEFT JOIN [{MERCH_SCHEMAID}].BM_STORE_M M 
ON D.STORE_NO = M.STORE_NO
LEFT JOIN [B116].BM_DIFF_M R
ON D.DIFF_FLG = R.DIFF_FLG
WHERE 1=1 
AND RCPT_DATE = '' 
AND D.CPT_DATE BETWEEN '{START_DATE}' AND '{END_DATE}'
AND D.STORE_NO IN ('{STORE_NO_6}')
GROUP BY D.STORE_NO,M.STORE_NO,D.DIFF_FLG,R.DIFF_DESC

-- 查詢路線剔退建檔
SELECT D.STORE_NO As 未清分路線代碼,
COUNT(*) As 被剔除待補清分筆數,
CASE WHEN M.STORE_NO IS NULL THEN '建立路線和補清分' ELSE '已建立路線待補清分' END As 狀況
FROM [{MERCH_SCHEMAID}].TM_SKIP_TMLOG_D D
LEFT JOIN [{MERCH_SCHEMAID}].BM_STORE_M M 
ON D.STORE_NO = M.STORE_NO
WHERE DIFF_FLG= '6005' AND RCPT_DATE = '' 
AND D.CPT_DATE BETWEEN '{START_DATE}' AND '{END_DATE}'
AND D.STORE_NO = '{STORE_NO_6}'
GROUP BY D.STORE_NO,M.STORE_NO,D.DIFF_FLG
```

比對細節
- 業者結構碼必須來自 query-bus.prompt.md 的唯一命中結果。
- `STORE_NO` 必須為 6 碼字串，不可省略前導零。
- 預設只檢查路線是否建檔，不根據問題中的地區詞自行加上條件；使用者明確要求限定地區時才套用對應欄位條件。
- 第 5) 步的兩段剔退查詢，每次產生第 3) 步 SQL 時一併輸出，不需使用者額外要求。

範例對話
- 使用者: 北客新北路線9908路線是否有建檔
- 助手:

```sql
SELECT * FROM [B102].BM_STORE_M WHERE STORE_NO IN ('009908')

-- 查詢剔退明細
SELECT 
D.STORE_NO As 未清分路線代碼,
D.DIFF_FLG As 剔退代碼,
R.DIFF_DESC As 剔退原因
FROM [B102].TM_SKIP_TMLOG_D D
LEFT JOIN [B102].BM_STORE_M M 
ON D.STORE_NO = M.STORE_NO
LEFT JOIN [B116].BM_DIFF_M R
ON D.DIFF_FLG = R.DIFF_FLG
WHERE 1=1 
AND RCPT_DATE = '' 
AND D.CPT_DATE BETWEEN '20260901' AND '20260930'
AND D.STORE_NO IN ('009908')
GROUP BY D.STORE_NO,M.STORE_NO,D.DIFF_FLG,R.DIFF_DESC

-- 查詢路線剔退建檔
SELECT D.STORE_NO As 未清分路線代碼,
COUNT(*) As 被剔除待補清分筆數,
CASE WHEN M.STORE_NO IS NULL THEN '建立路線和補清分' ELSE '已建立路線待補清分' END As 狀況
FROM [B102].TM_SKIP_TMLOG_D D
LEFT JOIN [B102].BM_STORE_M M 
ON D.STORE_NO = M.STORE_NO
WHERE DIFF_FLG= '6005' AND RCPT_DATE = '' 
AND D.CPT_DATE BETWEEN '20260901' AND '20260930'
AND D.STORE_NO = '009908'
GROUP BY D.STORE_NO,M.STORE_NO,D.DIFF_FLG
```

- 使用者: 首都客運101路線是否建檔
- 助手:

```sql
SELECT * FROM [B101].BM_STORE_M WHERE STORE_NO IN ('000101')
```

- 使用者: 北客9908路線名稱與起迄點
- 助手:

```sql
SELECT STORE_NO, STO_NAME_SHORT, STO_NAME_LONG FROM [B102].BM_STORE_M WHERE STORE_NO IN ('009908')
```
