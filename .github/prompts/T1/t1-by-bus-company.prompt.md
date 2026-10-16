---
mode: ask
description: 依客運名稱自動對照並輸出 T1 SQL
---

## 目標

當使用者只提供客運名稱（例如：首都客運）時，先從對照文件找出 `MERCHANT_NO` 與 `MERCH_SCHEMAID`，再組出可直接查詢 T1 資料來源的 SQL。

## 對照來源

- `schema/BBG客運路線對照.md`
- `正式機/T1/T1_explain.md`

## 規則

1. 先依客運名稱到 `BBG客運路線對照.md` 找出：
   - `MERCHANT_NO`
   - `MERCH_SCHEMAID`（即 schema，如 `B101`）
2. 若對照不到，先回覆「找不到對應業者，請補完整名稱或 MERCHANT_NO」。
3. 預設 `TR_SYSTEM_ID = '03'`。
4. `PAYMENT_TYPE` 對應：
   - 電票：`[schema].RPT_SETTLE_DATA_D_FOR_T1`
   - 電支：`[dbo].RPT_ICP_SETTLE_DATA_D_FOR_T1`
   - 全部：UNION ALL 上述兩表
5. `OPERATE_TYPE` 由 `S1.OPERATE_TYPE IN (...)` 控制（常見 `('01','02','03')`）。
6. 只輸出 SQL，不要額外解說。

## 電文回查輸出要求

1. 若使用者提供 T1 電文，先解析並帶出至少下列鍵值：
  - `BUSINESS_DATE`
  - `WORKING_DATE`
  - `FILE_CptDate`（即 `CPT_DATE`）
  - `StoreNo`
  - `DriverNo`
  - `Payment_Type`
2. 預設輸出 2 段 SQL：
  - `[schema].TM_SETTLE_DATA_D`
  - `[schema].RPT_SETTLE_DATA_D_FOR_T1`
3. 若使用者要求「精準命中單筆」，自動加上條件：
  - `MERCHANT_NO`
  - `BUSINESS_DATE`
  - `CPT_DATE`
  - `IS_ACT = 'Y'`

## 輸入參數

- `{MERCHANT_NAME}`：客運名稱（例如 首都客運）
- `{CPT_DATE}`：清分日（YYYYMMDD）
- `{PAYMENT_TYPE}`：電票 / 電支 / 全部
- `{OPERATE_TYPE_LIST}`：例如 `'01','02','03'`
- `{YYYYMM}`：可選，若要限制營業月份可加 `BUSINESS_DATE LIKE '{YYYYMM}%'`

## SQL 輸出模板

```sql
-- resolved from BBG客運路線對照.md
-- MERCHANT_NAME = {MERCHANT_NAME}
-- MERCHANT_NO   = {MERCHANT_NO}
-- SCHEMA        = {MERCH_SCHEMAID}

SELECT
  D1.BUSINESS_DATE,
  RIGHT(REPLICATE('0', 5) + CONVERT(VARCHAR, CONVERT(INT, D1.STORE_NO)), 5) AS StoreNo,
  D1.CPT_DATE,
  D1.WORKING_DATE,
  D1.DRIVER_NO,
  D1.LICENSE_NO,
  S1.OPERATE_TYPE,
  CASE WHEN S1.OPERATE_TYPE IN ('01','02') THEN 'T' ELSE 'F' END AS line_state,
  '{PAYMENT_TYPE}' AS PaymentSource
FROM (
  -- PAYMENT_TYPE = 電票
  SELECT *
  FROM [{MERCH_SCHEMAID}].RPT_SETTLE_DATA_D_FOR_T1
  WHERE '{PAYMENT_TYPE}' IN ('電票','全部')

  UNION ALL

  -- PAYMENT_TYPE = 電支
  SELECT *
  FROM [dbo].RPT_ICP_SETTLE_DATA_D_FOR_T1
  WHERE '{PAYMENT_TYPE}' IN ('電支','全部')
) D1
INNER JOIN [{MERCH_SCHEMAID}].BM_STORE_M S1
  ON D1.STORE_NO = S1.STORE_NO
 AND D1.MERCHANT_NO = S1.MERCHANT_NO
WHERE D1.MERCHANT_NO = '{MERCHANT_NO}'
  AND D1.CPT_DATE <= '{CPT_DATE}'
  AND D1.IS_ACT = 'Y'
  AND S1.OPERATE_TYPE IN ({OPERATE_TYPE_LIST})
  -- optional month filter
  -- AND D1.BUSINESS_DATE LIKE '{YYYYMM}%'
ORDER BY D1.BUSINESS_DATE, D1.CPT_DATE, StoreNo;
```

## 電文回查 SQL 模板

```sql
SELECT *
FROM [{MERCH_SCHEMAID}].TM_SETTLE_DATA_D
WHERE WORKING_DATE = '{WORKING_DATE}';

SELECT *
FROM [{MERCH_SCHEMAID}].RPT_SETTLE_DATA_D_FOR_T1
WHERE WORKING_DATE = '{WORKING_DATE}';
```

```sql
SELECT *
FROM [{MERCH_SCHEMAID}].TM_SETTLE_DATA_D
WHERE MERCHANT_NO   = '{MERCHANT_NO}'
  AND BUSINESS_DATE = '{BUSINESS_DATE}'
  AND WORKING_DATE  = '{WORKING_DATE}';

SELECT *
FROM [{MERCH_SCHEMAID}].RPT_SETTLE_DATA_D_FOR_T1
WHERE MERCHANT_NO   = '{MERCHANT_NO}'
  AND BUSINESS_DATE = '{BUSINESS_DATE}'
  AND CPT_DATE      = '{CPT_DATE}'
  AND WORKING_DATE  = '{WORKING_DATE}'
  AND IS_ACT        = 'Y';
```

## 首都客運示例

已知：
- `MERCHANT_NAME = 首都客運`
- `MERCHANT_NO = 34049262`
- `MERCH_SCHEMAID = B101`

請依模板將 `{MERCHANT_NO}` 改為 `34049262`、`{MERCH_SCHEMAID}` 改為 `B101` 再輸出 SQL。
