# 修改 Section 的 sqlfile 參數

請依照我提供的參數，修改指定 Section 內的 sqlfile 參數集合。

## 輸入方式
你可以用以下任一種方式提供需求：

1. 固定欄位格式
2. 自然語言描述

若能明確辨識出以下 3 個必要參數，就直接執行修改：
- `section`
- `sql_path`
- `insert_order`

若缺少任一必要參數，先用最少問題向我確認，不要自行猜測。

## 固定欄位格式
請用以下格式提供：

```text
file: <可選，目標檔案路徑>
section: <Section 名稱>
sql_path: <要插入的 sql 路徑>
insert_order: <要插入為第幾個分頁，從 1 開始>
```

## 自然語言格式
也接受這種說法：

```text
幫我修改 Section OMSH_Tycg_GENM_EXL_0301_B304
加入 sql\GRANT_Tycg\EXL_0301_sum.sql
插入第一個分頁
```

或：

```text
在 OMSH_Tycg_GENM_EXL_0301_B304 裡面
把 sql\GRANT_Tycg\EXL_0301_sum.sql 加到第 1 個分頁
```

或：

```text
幫我在 Section OMSH_Tycg_GENM_EXL_0301_B304 的 sqlfile 參數中
新增 sql\GRANT_Tycg\EXL_0301_sum.sql
放在最前面
```

## 自然語言解析規則
- `section`：優先從 `Section <名稱>`、`在 <名稱> 裡面`、`修改 <名稱>` 這類語句辨識。
- `sql_path`：優先抓取看起來像 sql 路徑的內容，例如 `sql\...\.sql`。
- `insert_order`：接受以下常見說法：
   - `第 1 個分頁`
   - `第一個分頁`
   - `放最前面`
   - `插在最前面`
   - `插入第 3 個分頁`
- 若同一句話出現多個可能的 Section、sql 路徑或順序，只能在明確唯一時才執行；否則先詢問。
- 若自然語言與固定欄位同時出現且內容衝突，以固定欄位格式為準，並在回覆中指出衝突。

如果我沒有提供 file：
- 先在工作區搜尋包含該 Section 名稱的檔案。
- 若只找到 1 個檔案，直接修改。
- 若找到多個檔案，先列出候選檔案並要求我確認，不要直接修改。
- 若找不到檔案，明確告知找不到的 Section。

## 修改範圍
- 只修改指定 Section 內的參數區塊。
- 不要修改其他 Section。
- 不要修改與 sqlfile 無關的設定。

## 修改邏輯
1. 找出該 Section 內的 `sqlfile_amount`。
2. 找出該 Section 內所有 `sqlfileN=` 參數，依目前序號排序。
3. 將 `sqlfile_amount` 加 1。
4. 將新的 sqlfile 插入到 `insert_order` 指定的位置。
5. 重新編排全部 `sqlfileN`：
   - 參數名稱尾碼 `N` 必須從 1 開始連號。
   - 每個 `sqlfile` 值中的第 2 個欄位，也就是分頁序號，也必須從 1 開始連號。
6. 新增的 sqlfile 內容格式如下：
   - 第 1 個欄位：使用 `sql_path`
   - 第 2 個欄位：依重排後的分頁序號
   - 第 3 到第 6 個欄位：沿用該 Section 既有 sqlfile 的格式
7. 若既有 `sqlfile` 的第 3 到第 6 個欄位不完全一致：
   - 預設沿用插入位置前後最接近的一筆
   - 若仍無法明確判斷，先停止並說明差異，不要自行假設

## 邊界規則
- `insert_order=1` 代表插入成第一個分頁。
- `insert_order` 若大於目前筆數 + 1，停止並告知參數超出範圍。
- `insert_order` 若小於 1，停止並告知參數不合法。
- 若 Section 內沒有 `sqlfile_amount` 或沒有任何 `sqlfileN`，先停止並說明原因，不要自行補整段格式。

## 輸出要求
- 直接修改檔案。
- 回覆時簡短說明：
  - 修改了哪個檔案
  - 哪個 Section 被修改
  - 插入了哪個 sql_path
  - 插入為第幾個分頁
- 額外回報以下驗證結果：
  - `sqlfile_amount` 是否等於實際 `sqlfile` 筆數
  - `sqlfile1 ... sqlfileN` 是否連號
  - 每筆內容中的分頁序號是否連號且與 `sqlfileN` 一致

## 範例

輸入：
```text
section: OMSH_Tycg_GENM_EXL_0301_B304
sql_path: sql\GRANT_Tycg\EXL_0301_sum.sql
insert_order: 1
```

原始內容：
```text
sqlfile_amount=2
■SQL檔格式：1.SQL檔路徑參數 2.分頁序號 3.方格起始位置 4.字型 5.字體大小 6.新增列■
sqlfile1=sql\GRANT_Tycg\EXL_0301.sql|1|3,1|標楷體|12|ADDROW
sqlfile2=sql\GRANT_Tycg\EXL_0301_1.sql|2|3,1|標楷體|12|ADDROW
```

期望修改後：
```text
sqlfile_amount=3
■SQL檔格式：1.SQL檔路徑參數 2.分頁序號 3.方格起始位置 4.字型 5.字體大小 6.新增列■
sqlfile1=sql\GRANT_Tycg\EXL_0301_sum.sql|1|3,1|標楷體|12|ADDROW
sqlfile2=sql\GRANT_Tycg\EXL_0301.sql|2|3,1|標楷體|12|ADDROW
sqlfile3=sql\GRANT_Tycg\EXL_0301_1.sql|3|3,1|標楷體|12|ADDROW
```

## 呼叫範例
```text
/insert-section-sqlfile
section: OMSH_Tycg_GENM_EXL_0301_B304
sql_path: sql\GRANT_Tycg\EXL_0301_sum.sql
insert_order: 1
```

也可以直接用自然語言呼叫：

```text
/insert-section-sqlfile
幫我修改 Section OMSH_Tycg_GENM_EXL_0301_B304 內參數部分
加入 sql\GRANT_Tycg\EXL_0301_sum.sql
參數為第一個分頁
```

如果你已知檔案，也可以這樣提供：

```text
/insert-section-sqlfile
file: path\to\target.ini
section: OMSH_Tycg_GENM_EXL_0301_B304
sql_path: sql\GRANT_Tycg\EXL_0301_sum.sql
insert_order: 1
```
