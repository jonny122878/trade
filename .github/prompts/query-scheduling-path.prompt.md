---
name: query-scheduling-path
description: "從 schema/Scheduling/10_189_162_4.csv 查詢 Windows 排程路徑，依台北捷運乘車碼或儲值卡條件執行 DuckDB SQL 並輸出 CSV，且將執行工作與開始位置改成備份路徑。"
---

# 查詢排程所在路徑

## 目的

使用 DuckDB 查詢 `schema/Scheduling/10_189_162_4.csv`，依使用者描述找出 Windows 工作排程，將路徑替換後實際輸出 CSV。SQL、輸出檔路徑與查詢結果摘要也要一併回傳。

## 使用者輸入

使用者至少要提供：

- 查詢項目：例如 `台北捷運乘車碼` 或 `查台北捷運儲值卡`
- 要查詢日期：格式為 `YYYYMMDD`，例如 `20260921`

若缺少查詢日期，先要求使用者補充，不要自行猜日期。


查詢模板：

```sql
WITH params AS (
    SELECT '20260919' AS query_date
)
SELECT
    "開始位置" AS "原開始位置",
    CASE
        WHEN regexp_matches("開始位置", '\\bat\\$') THEN
            regexp_replace(
                "開始位置",
                '\\bat\\$',
                '\\bkup\\' || params.query_date
            )
        ELSE "開始位置"
    END AS "開始位置"
FROM read_csv_auto(
    'schema/Scheduling/10_189_162_4.csv',
    header = true,
    delim = ',',
    quote = '"'
)
CROSS JOIN params
WHERE starts_with("註解", '電支_北捷');
```

## 路徑替換規則

查詢日期以使用者輸入的 `YYYYMMDD` 代入 `<query_date>`。

輸出路徑依使用者指定的報表類型判斷，`{日期}` 代入使用者輸入的 `YYYYMMDD`：

- 特別指定 `T1`：`D:\ICMS_Batch\B113\ICMS\bkup\{日期}\OUT_GRANT_D`
- 日結報表：`D:\ICMS_Batch\B113\ICMS\bkup\{日期}\OUT_PDF_D`
- 未指定 `T1` 或日結報表：`D:\ICMS_Batch\B113\ICMS\bkup\{日期}\OUT`

若同時出現多個描述，優先套用明確指定的報表類型；T1 優先於日結報表，其他情況使用一般 `OUT` 路徑。


## 範例

使用者：

```text
查台北捷運儲值卡，日期 20260921
```

應使用：

```text
註解前綴 = '帳務清分'
查詢日期 = 20260921
```

使用者：

```text
台北捷運乘車碼，日期 20260921
```

應使用：

```text
註解前綴 = '電支_北捷'
查詢日期 = 20260921
```
