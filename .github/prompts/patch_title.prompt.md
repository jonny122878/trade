# patch_title.prompt

目的：對 reportctl.ini 的各 Section 區塊，檢查 title / sqlfile 相關欄位，當符合條件時產生 patch（修改建議）。

使用方式：輸入一個 Section 群組的內容（或整個 reportctl.ini），本 prompt 會
- 檢核每個區塊（Section）內的 `sqlfile`、`title`、`sqlfile_amount`、`title_amount` 等欄位
- 依規則判定是否需要修改，若需修改則輸出 patch 建議（純文本 diff-like）

檢核與修改規則：
1. 若 `title_amount` == 0 → 不做任何修改（視為 intentionally empty）
2. 若 `sqlfile_amount` 與 `title_amount` 不相等：
   - 將 `title_amount` 設定為 `sqlfile_amount`（也可以選擇只回報，依參數決定）
3. 確保 `title` 集合內的元素序列為遞增命名：`title1`, `title2`, `title3`, ...
   - 若命名不符合，重新產生從 `title1` 起的序列，元素總數與 `sqlfile_amount` 一致
4. 確保 `title` 中代表「分頁序號」的數值（若存在於元素值中）為遞增順序
   - 例：`第1頁/共3頁`、或 `page 1/3` → 檢查每一個 title 的頁號是否遞增

輸出格式（patch 建議）：
- 對於每一個需要變更的 Section，輸出一個 block：

Section: [SECTION_NAME]
- Action: 修改 `title_amount` from X to Y
- Action: 重新命名 `title` 元素
  - old: ["...","...",...]
  - new: ["title1","title2",...]

範例工作流程（演算法概要）：
1. 以 Section header 當作分群組依據，逐 Section 處理
2. 解析出 `sqlfile` 列表與 `title` 列表，並讀取 `sqlfile_amount`、`title_amount`
3. 如果 `title_amount` == 0，記錄為 skip，下一個 Section
4. 比對 `sqlfile_amount` 與 `title_amount`：若不同，產生修改 `title_amount` 的 patch
5. 檢查 `title` 命名序列：
   - 若名為 `titleX` 型式但不連續，或名稱非 `titleX`，產生重新命名 patch
6. 檢查 `title` 中之分頁序號是否遞增：若不是，產生修正建議（保留原文字，但修正數字順序）
7. 新增的 title 元素應在 title_amount 和 path_out 元素之間
8. 不要去異動 title 元素值的其他部分（如分頁文字），除非分頁序號不正確，則只修改數字部分
注意事項：
- 只有當檢核結果需要變更時才回傳 patch 建議，其他保持原樣
- 修改建議建議以最小變動原則（只變更多錯誤的欄位）

---
請用中文回應，僅對符合上述規則的區塊輸出 patch 建議；`title_amount=0` 則跳過。
