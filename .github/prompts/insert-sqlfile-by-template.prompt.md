# 依 template_name 批次修改 sqlfile 參數

請依照我提供的條件，自動搜尋 reportctl.ini，並對符合條件的 Section 批次修改 sqlfile 參數。

## 適用情境
- 你想一次修改多個 Section。
- 每個 Section 的篩選條件是 `template_name`。
- 每個命中 Section 都套用同一個 `sql_path` 與 `insert_order`。

## 輸入方式
你可以用以下任一種方式提供需求：

1. 固定欄位格式
2. 自然語言描述

若能明確辨識出以下 3 個必要參數，就直接進入掃描：
- `template_name_match`
- `sql_path`
- `insert_order`

若缺少任一必要參數，先用最少問題向我確認，不要自行猜測。

## 固定欄位格式
請用以下格式提供：

```text
file: <可選，reportctl.ini 的路徑>
template_name_match: <template_name 完整值或關鍵字>
match_mode: <EXACT 或 CONTAINS，預設 CONTAINS>
sql_path: <要插入的 sql 路徑>
insert_order: <要插入為第幾個分頁，從 1 開始>
```

## 自然語言格式
也接受這種說法：

```text
幫我在 reportctl.ini 裡
找 template_name 包含 表一-2_補貼款申請表_非市民卡_含電支.xlsx 的 section
把 sql\GRANT_Tycg\EXL_0301_sum.sql 插入第一個分頁
```

或：

```text
用 template_name 關鍵字 表二_營運月報明細表
命中的區塊都加上 sql\GRANT_Tycg\EXL_0302_sum.sql
放第 1 個分頁
```

## 搜尋規則
1. 若有提供 `file`，只掃描該檔。
2. 若未提供 `file`：
   - 先在工作區搜尋名為 `reportctl.ini` 的檔案。
   - 若只找到 1 個，直接使用。
   - 若找到多個，先列出候選清單並要求我確認，不要直接修改。
   - 若找不到，明確告知。
3. `match_mode=EXACT`：`template_name` 必須完全相同。
4. `match_mode=CONTAINS`：`template_name` 包含關鍵字即可。

## 執行流程（重要）
1. 掃描命中 Section 後直接執行修改，不需先預覽或二次確認。
2. 若命中 0 筆，停止並回報。
3. 先做冪等判斷：若某 Section 已符合目標狀態，直接略過不修改。
   - 目標狀態判斷條件：
   - `insert_order` 指定位置的 sqlfile 為 `sql_path`
   - `sqlfile_amount` 等於實際 sqlfile 筆數
   - `sqlfile1 ... sqlfileN` 與每筆第 2 欄分頁序號都已連號且一致
   - 若以上條件都成立，標記為 `SKIPPED_ALREADY_MATCHED`
4. 對未被略過的命中 Section 套用以下修改邏輯：
   - 找出 `sqlfile_amount`
   - 找出所有 `sqlfileN=`
   - `sqlfile_amount` 加 1
   - 將 `sql_path` 插入 `insert_order`
   - 重新編排 `sqlfile1 ... sqlfileN`
   - 同步重排每筆值中的第 2 個欄位（分頁序號）
5. 新增項目格式：
   - 第 1 欄：`sql_path`
   - 第 2 欄：重排後分頁序號
   - 第 3 到第 6 欄：沿用該 Section 既有 sqlfile 格式
6. 若既有第 3 到第 6 欄不一致：
   - 預設沿用插入位置前後最接近的一筆
   - 若仍無法判斷，先停止並回報該 Section，不要自行猜測

## 邊界規則
- `insert_order=1` 代表插入第一個分頁。
- `insert_order` 若大於「該 Section 目前筆數 + 1」，該 Section 視為失敗並回報原因。
- `insert_order` 若小於 1，直接停止並回報參數不合法。
- 若某 Section 缺少 `sqlfile_amount` 或沒有任何 `sqlfileN`，該 Section 視為失敗並回報，不要自行補格式。
- 單一 Section 失敗不應中止其他可成功 Section；最後要提供成功/失敗摘要。
- 若 Section 已在目標狀態，必須略過，不得重複插入相同 sql_path。

## 修改範圍
- 只修改命中 Section 內與 `sqlfile` 相關參數。
- 不要修改其他 Section。
- 不要修改 title、file_name、template_name 等非 sqlfile 參數。

## 輸出要求
完成後請回覆：
1. 使用的 reportctl.ini 檔案
2. 命中 Section 數量
3. 成功修改 Section 清單
4. 略過 Section 清單（`SKIPPED_ALREADY_MATCHED`）
5. 失敗 Section 清單與原因
6. 每個成功 Section 的驗證結果：
   - `sqlfile_amount` 是否等於實際 sqlfile 筆數
   - `sqlfile1 ... sqlfileN` 是否連號
   - 每筆內容第 2 欄分頁序號是否連號且與 `sqlfileN` 一致

## 呼叫範例（固定欄位）
```text
/insert-sqlfile-by-template
file: 正式機\_ICASH_TR_TYCG\_ICMS_RPT\parm\ini\reportctl.ini
template_name_match: 表一-2_補貼款申請表_非市民卡_含電支.xlsx
match_mode: EXACT
sql_path: sql\GRANT_Tycg\EXL_0301_sum.sql
insert_order: 1
```

## 呼叫範例（自然語言）
```text
/insert-sqlfile-by-template
幫我搜尋 reportctl.ini
template_name 包含 表二_營運月報明細表_含電支.xlsx 的所有區塊
加入 sql\GRANT_Tycg\EXL_0302_sum.sql
放在第一個分頁
```
