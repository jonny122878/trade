---
name: code-review
description: "產出 Code Review 分析報告。Use for: code review, review branch, review PR, review commit diff, 上線前 review, 分析程式風險, diff 風險分析, branch 變更審查, ICP code review, review 這段程式, 幫我 review。Covers: 六大強制分析角度（架構耦合、API/DB相容性、資料一致性、權限安全、可維運性、DB效能）、風險等級定義、報告格式規範、Missing Index 逐欄檢查。"
argument-hint: "指定比較範圍：<base_commit>..<target_branch> 或 branch 名稱，以及目標環境（dev/uat/stage/prod）"
---

# Code Review 分析報告產出規範

## 觸發時機

使用者明確要求 code review，或提供以下任一訊息時啟動此 SKILL：

- 「code review commit A 和 commit B 之後的差異」
- 「幫我 review 這個 branch 的變更」
- 「分析這次 PR / diff 的風險」
- 「上線前幫我做一次 code review」

---

## 前置資訊收集

| 必要資訊 | 取得方式 |
|---------|---------|
| **分析分支名稱** | `git branch --show-current` |
| **比較基準 commit** | 使用者提供，或 `git log --oneline -5` |
| **受審 Repo 清單** | 使用者提供，或依 commit hash 找到所屬 repo |
| **分析日期** | 系統日期（`YYYYMMDD`） |
| **目標環境** | 詢問使用者（dev / uat / stage / prod） |

---

## Diff 取得方式

```powershell
# 單一 repo
git -C "<repo_path>" diff <base_commit>..origin/<target_branch> --stat
git -C "<repo_path>" diff <base_commit>..origin/<target_branch>

# 查看變更的檔案清單
git -C "<repo_path>" diff <base_commit>..origin/<target_branch> --name-only
```

---

## 六大強制分析角度

每次 Code Review **必須涵蓋**以下六個面向，不得省略。

### 1. 架構耦合風險

- 模組間職責是否清晰？有無不適當的強耦合？
- Factory / Strategy / Interface 等設計模式是否正確使用？
- 靜態狀態（Static fields）是否在多模組間共用？

### 2. API / DB 相容性風險

- 前後端 API 契約（request / response schema）是否同步？
- 資料庫 Schema（欄位、型別、UNIQUE 約束）是否支援新邏輯？
- 環境設定（prod / uat）是否正確，有無遺留測試設定？
- Config / 外部 JSON 的欄位新增，有無向下相容設計？

### 3. 資料一致性與重複寫入風險

- 跨多個集合 / 表的寫入是否具原子性？
- Cache 清除與重建之間是否存在空窗期？
- 磁碟 / 外部儲存的寫入是否有順序依賴或部分失敗問題？

### 4. 權限與安全風險

- 是否有金鑰、密碼、Token 硬編碼進原始碼（或 Git 歷史）？
- Query String 或 Header 的身份參數是否有簽章驗證？
- 授權邏輯是否被弱化或移除？
- OWASP Top 10 中的注入、存取控制等是否可能觸發？

### 5. 可維運性（Log / 監控）

- 核心業務路徑（寫入成功 / 失敗）是否有 log 記錄？
- 例外是否被靜默吞掉（catch 後無 log）？
- Log 輸出通道是否有備援（單點故障）？
- Application Insights / 監控告警是否覆蓋關鍵 KPI？

### 6. DB 效能風險

**每次涉及 SQL / SP / Query 變更時必須執行此分析，不得省略。**

#### 6-1. Missing Index 檢查

對照**每一個新增或修改的 WHERE / JOIN ON / ORDER BY 條件欄位**，逐一到 `ICP_SP/TABLE/` 目錄確認對應 TABLE 的 Index 定義（`.Table.sql`）。

- WHERE 條件欄位不在任何 Index 的 Key 欄位中 → Missing Index（依資料量判斷 🔴/🟠）
- OR 條件（`A = x OR B = x`）：需對 A、B 各有獨立 Index，SQL Server 才能執行 Union Seek
- LEFT JOIN 的 ON 條件欄位：同 WHERE 規則
- ORDER BY 欄位：若無 Index 對應，大資料量會觸發 Sort 運算（🟡）

#### 6-2. JOIN 類型語意確認

- `INNER JOIN` vs `LEFT JOIN` 的選擇是否符合業務語意？
- 條件放在 `ON` vs `WHERE` 子句對 LEFT JOIN 語意影響截然不同（WHERE 過濾 NULL 行 = 等效 INNER JOIN）
- CROSS JOIN / 無 ON 子句的 JOIN 是否為已知且預期的行為？

#### 6-3. 查詢範圍與掃描風險

- 是否有移除原本的過濾條件（如 `MemberStatus = 1`）？移除後資料集是否顯著擴大？
- `SELECT *` 是否出現在非臨時腳本中？
- `WITH(NOLOCK)` 使用是否合理，是否在高並發 INSERT 路徑旁使用？
- 分頁機制（`TOP n`、`OFFSET...FETCH`）是否正確，有無全量撈取風險？

#### 6-4. Index 腳本品質

- `DROP_EXISTING = ON` vs `OFF`：上版腳本建議統一使用 `ON` 以支援安全重跑
- `ONLINE = ON/OFF`：`OFF` 建立期間鎖表，需在業務空窗期執行；需在部署計畫中標注
- 腳本中的注解名稱是否與實際 `CREATE INDEX` 名稱一致
- 是否有 `GO` 分隔符（自動化部署工具需要）

---

## 額外選用分析角度（依變更性質判斷）

| 角度 | 觸發條件 |
|------|---------|
| **重複寫入 / 非冪等** | 有 DB Insert、Queue 消費、外部 API 呼叫 |
| **併發衝突** | 有 static 共用狀態、無鎖的 Check-then-Act 模式 |
| **破壞性變更 / 部署順序** | 有 Config Schema 新增、API Response 結構異動、DB 欄位變更 |
| **效能影響** | 有常數放大、全量 Cache 刷新、無分頁 render |
| **測試覆蓋率** | 有核心業務邏輯變更，可見單元測試或整合測試 |

---

## 風險等級定義

| 等級 | 定義 | 範例 |
|------|------|------|
| 🔴 **阻擋上線** | 直接導致資安破口、生產環境打錯、資料遺失 | 金鑰硬編碼、env=uat 未修 |
| 🟠 **高風險** | 高機率觸發資料錯誤、並發異常、靜默失敗 | 無 UNIQUE 約束、Clear 在 lock 外 |
| 🟡 **中風險** | 低機率觸發或影響範圍有限，但需在未來迭代中修正 | 時間邏輯不一致、log 覆蓋不足 |
| 🟢 **低風險** | 技術債、可讀性問題、文件不一致，可在下次重構時處理 | Console.log 殘留、死注解 |

---

## 報告輸出規則

### 檔名格式

```
CodeReview_<分支名稱>_<YYYYMMDD>.md
```

### 必要章節（不得省略）

1. **報告標頭表格**：分析日期、分析分支、受審 Repo、比較基準、審查人
2. **目錄**（含錨點）
3. **變更摘要**（每個 Repo 一個表格，列出每個檔案的變更內容）
4. **六大風險分析章節**（各小節需有：位置 → 問題描述 → 程式碼片段 → 建議修正）
5. **綜合風險總表**（所有問題依優先級排序，至少含：優先級、面向、問題、位置）
6. **建議修補清單**（Blocker / High / Medium 三層，以 `- [ ]` checkbox 呈現）

### 程式碼片段格式

每個問題**必須**附上問題程式碼，若有修正建議附上修正後程式碼：

```csharp
// 問題：說明問題所在
PROBLEMATIC_CODE_HERE

// 修正建議：
SUGGESTED_FIX_HERE
```

### 報告底部署名

```markdown
*本報告由 GitHub Copilot 自動分析產出，涵蓋 commit `<base>→<target>`（<Repo>）的所有差異。*
```

報告範本見：[CodeReview_TEMPLATE.md](../CodeReview_TEMPLATE.md)

---

## 分析深度要求

### 必須做的事

- 實際讀取每一個變更檔案的完整內容（不只看 diff 摘要）
- 追蹤呼叫鏈（A 呼叫 B，B 的問題也要追蹤）
- 確認 DB Schema（是否有 UNIQUE / PK 約束）
- DB 效能（SQL/SP 異動時）：逐欄比對 WHERE / JOIN ON / ORDER BY 欄位，對照 `ICP_SP/TABLE/*.Table.sql` 確認每個欄位是否有對應 Index
- 確認環境設定字串（prod / uat / hardcoded key）
- 確認並發路徑（同一 API 兩次呼叫的競爭條件）

### 不能做的事

- 僅依 diff 摘要（`--stat`）做判斷，未讀實際程式碼
- 跳過安全掃描（金鑰、密碼搜尋）
- 省略任何一個必要章節
- 風險等級不標示或只說「待確認」

---

## 每次 Review 前檢查清單

### 安全性

- [ ] `git log --all -p -S "password\|secret\|key\|token\|AccountKey\|subscriptionKey"` 找硬編碼敏感資訊
- [ ] Query String 是否傳遞身份資訊（ICPMID、token）
- [ ] 授權邏輯（isEnable、startTime 等）是否被移除或弱化

### DB 效能（SQL / SP 有變更時必查）

- [ ] 所有新增 / 修改的 WHERE、JOIN ON、ORDER BY 欄位，對照 `ICP_SP/TABLE/*.Table.sql` 確認 Index 覆蓋
- [ ] OR 條件（`A = x OR B = x`）兩側是否各有獨立 Non-Clustered Index
- [ ] LEFT JOIN 的 ON 條件移動（vs WHERE）是否造成語意改變（NULL 行保留/過濾）
- [ ] 有無移除原本的 WHERE 過濾條件，造成掃描資料集擴大
- [ ] `WITH(NOLOCK)` 使用是否合理
- [ ] Index 腳本：`DROP_EXISTING = ON`、`ONLINE` 設定、注解名稱一致性、是否有 `GO`

### 資料正確性

- [ ] 新增的 DB Insert 路徑，DB 表是否有對應 UNIQUE 約束
- [ ] API Response 的 Schema 是否有 fallback，fallback 是否硬編碼過時資料
- [ ] Config 新欄位，程式碼是否有 null guard

### 可維運性

- [ ] 核心 try/catch 區塊是否有 log
- [ ] 背景 Task（fire-and-forget）是否有 try/catch
- [ ] Console.Write/WriteLine 是否出現在 IIS/Server 端
- [ ] log 輸出是否只有單一通道（無備援）

### 部署相依

- [ ] Config Schema 異動是否需要先更新外部設定（Blob / App Settings）
- [ ] DB Migration 是否需要在應用程式前執行
- [ ] 環境切換 commit 是否已 merge 至目標 branch

---

*此 SKILL 版本：v1.1（2026-04-02）*  
*v1.1 異動：新增第六大強制角度「DB 效能風險」，包含 Missing Index、JOIN 語意、查詢掃描範圍、Index 腳本品質四個子項。*
