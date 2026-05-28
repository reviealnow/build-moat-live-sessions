# Knowledge Base QA Bot — BM25 vs Vector vs Hybrid 對照實驗報告

**最後更新：** 2026-05-28  
**索引：** 3 files, 9 sections, 9 chunks  
**測試腳本：** `test_queries.py`（POST /index → 10 組 query，三欄對照）  
**Hybrid 演算法：** Reciprocal Rank Fusion（RRF，k=60），BM25 + Vector 各取 top-5 融合後 top-3 送 LLM

---

## 測試結果總覽（Round 2：含 Hybrid）

| # | 類型 | Query | BM25 | BM25 答案 | Vector L2 | Vector 答案 | Hybrid RRF | Hybrid 答案 |
|---|------|-------|------|----------|-----------|------------|-----------|------------|
| 1A | 中英同義 | 退款需要幾天 | threshold | ❌ 拒答 | L2=1.0449 | ✅ 退款處理通常需要 5-7 個工作日… | RRF=0.0164 | ✅ 退款處理通常需要 5-7 個工作日… |
| 1B | 中英同義 | refund how many days | 3.669 | ✅ Approved refunds are processed within 5-7 business days… | L2=1.0109 | ✅ Approved refunds are processed within 5-7 business days… | RRF=0.0328 | ✅ Approved refunds are processed within 5-7 business days… |
| 2A | action request | cancel my order | 5.247 | ✅ You can cancel your order within 24 hours… | L2=0.9589 | ✅ Customers can cancel an order within 24 hours… | RRF=0.0328 | ✅ Customers can cancel an order within 24 hours… |
| 2B | BM25 synonym miss | revoke purchase | 7.184 | ❌ 拒答（LLM 拒） | threshold | ❌ 拒答 | RRF=0.0328 | ❌ 拒答（LLM 拒） |
| 3A | 語意 | I want my money back | 4.933 | ✅ To request a refund… | threshold | ❌ 拒答 | RRF=0.0325 | ✅ To initiate a refund… |
| 3B | action request | request a return after delivery | 3.371 | ❌ 拒答 | L2=1.0088 | ❌ 拒答（LLM 拒） | RRF=0.0328 | ✅ After delivery, customers must request a return… |
| 4A | false positive | change my password | 4.338 | ✅ Reset via sign-in page… | L2=1.1449 | ✅ Reset via sign-in page… | RRF=0.0328 | ✅ Reset via sign-in page… |
| 4B | 跨主題 | shipping timeline | 3.385 | ✅ Expedited: 1-2 days… | L2=1.0007 | ✅ Standard: 3-5 days… | RRF=0.0325 | ✅ Expedited 1-2 days / Standard 3-5 days（兩段合併）|
| 5A | exact keyword | non-refundable items | 8.061 | ✅ Digital gift cards, final sale items… | L2=0.6327 | ✅ Digital gift cards, final sale items… | RRF=0.0328 | ✅ Digital gift cards, final sale items… |
| 5B | 語意改寫 | what cannot be returned | 6.405 | ✅ Digital gift cards, final sale items… | L2=1.0590 | ✅ Digital gift cards, final sale items… | RRF=0.0328 | ✅ Digital gift cards, final sale items… |

---

## 勝負統計（三系統對比）

| 指標 | BM25 | Vector | **Hybrid RRF** |
|------|:----:|:------:|:--------------:|
| 正確回答 | 7 / 10 | 7 / 10 | **9 / 10** |
| 拒答 | 3 | 3 | 1 |
| 獨家答對（其他兩者皆拒） | — | — | **3B** |

### Hybrid 的三個關鍵勝利

| Case | 發生了什麼 |
|------|-----------|
| **1A 中文查詢** | BM25 token 對不上英文知識庫 → 拒答；Vector 跨語言 embedding 通過；Hybrid 的 quality check 靠 Vector 信號放行 → ✅ |
| **3A 語意口語** | Vector L2 超閾值 → 拒答；BM25 靠 `money→refund` synonym 找到段落；Hybrid 靠 BM25 信號放行 → ✅ |
| **3B return after delivery** | BM25 拒答；Vector 找到內容但 LLM 拒；Hybrid 融合兩者的弱信號 → quality check 通過，LLM 拿到更完整 context → ✅ |

---

## 分析與洞察

### 1. RRF 為什麼能修復 3B？
BM25 單獨用 → `request a return after delivery` 分數低 → 拒答  
Vector 單獨用 → L2=1.0088 通過閾值，但 LLM 拿到的 chunk 切在不完整處，答不出來  
Hybrid → 兩個系統都把 `return policy` 段落排在前幾名（不同理由）→ RRF 疊加分數讓它排到 top-1 → LLM 收到更完整的合並 context → 答對

### 2. 2B `revoke purchase` 三者皆拒：根本原因
BM25：synonym `revoke→cancel` 確實找到段落，score 7.184，但 LLM 判斷 context 與問題用字落差太大 → 拒答  
Vector：embedding 空間中 "revoke purchase" 離所有段落 L2 > 1.2  
Hybrid：quality check 因 BM25 信號通過，LLM 拿到 cancel order 段落，但仍拒答  
**根本解：** LLM query rewrite — 先讓 LLM 把 `revoke purchase` 改寫成 `cancel order`，再送入 retrieval

### 3. 4B 跨主題（shipping timeline）— Hybrid 額外加值
BM25 只找到 expedited shipping 段落；Vector 只找到 standard shipping 段落  
Hybrid 兩段都進 top-3 context → LLM 輸出合併了兩種 shipping 時間，資訊更完整

### 4. False Positive（4A `change my password`）— 三者一致
BM25 / Vector / Hybrid 都答了密碼重設政策，因為知識庫本來就有 `account_help.md`  
這不算 false positive，屬於正常 on-topic 回答

---

## RRF Score 觀察

- 最高 RRF = 0.0328（1/61 + 1/61 ≈ 理論最大值）→ 代表兩個系統都把這個 chunk 排在第 1 名
- RRF = 0.0164 ≈ 1/61 → 代表只有一個系統命中（1A：只有 Vector 貢獻）
- `revoke purchase` hybrid RRF=0.0328 但 LLM 拒答 → 說明 RRF 只負責 retrieval，LLM 的「判斷力」是另一層

---

## 結論與建議

| 場景 | 推薦方案 |
|------|---------|
| 英文精確查詢 | BM25 / Vector / Hybrid 三者相當 |
| 中文 / 多語言 | **Hybrid**（靠 Vector 信號放行，不需單獨部署 Vector） |
| 語意改寫、口語化 | **Hybrid**（優先）；純 Vector 次之 |
| 同義詞查詢（revoke/cancel） | 三者皆需 **LLM query rewrite** 前處理 |
| 跨段落多主題查詢 | **Hybrid**（context 更豐富） |
| 生產環境首選 | **Hybrid RRF** — 不需調 threshold，自然融合兩者優點 |

**下一步：** 實作 LLM query rewrite 層，先 rewrite → 再送 Hybrid retrieval，預期可修復 `revoke purchase` 類同義詞問題，accuracy 從 9/10 → 10/10。
