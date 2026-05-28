# QR Code Generator — 資料拓樸圖

## Q1｜這個服務有開 DB 嗎？

**有，是真實的 SQLite 檔案**，路徑在 `scaffold/qr_code.db`。  
服務啟動時 `Base.metadata.create_all()` 會自動建立資料表，所有 token 與原始 URL 都**持久化到磁碟**，重啟不會消失。  
`redirect_cache` 是一個 Python `dict`，只是熱路徑的加速層（in-memory），服務重啟後會清空。

## Q2｜掃描次數的計數器在哪？

計數器**沒有獨立欄位**，而是用 `scan_events` 資料表的 row 數量做聚合：

- 每次 `GET /r/{token}` 成功 redirect，`_record_scan()` 就往 `scan_events` 插一筆 row（含 timestamp、IP、user-agent）
- `GET /api/qr/{token}/analytics` 用 `SELECT COUNT(*) ... GROUP BY date(scanned_at)` 即時算出每日掃描數

這種設計的好處是可以隨時做時間區間查詢，壞處是資料量大後 COUNT 會變慢（需要加 index，目前已有 `idx_token_scanned`）。

---

## Q3｜資料拓樸圖

```mermaid
flowchart TD
    Client(["Client\nBrowser / curl"])

    subgraph App ["FastAPI App  —  uvicorn :8000"]
        direction TB
        FE["GET /\nHTML Frontend"]
        RL["slowapi Rate Limiter\n10 req / min / IP\nin-memory counter"]
        CreateR["POST /api/qr/create"]
        RedirectR["GET /r/{token}"]
        InfoR["GET /api/qr/{token}"]
        UpdateR["PATCH /api/qr/{token}"]
        DeleteR["DELETE /api/qr/{token}"]
        ImageR["GET /api/qr/{token}/image"]
        AnalyticsR["GET /api/qr/{token}/analytics"]
        Cache[("Redirect Cache\ndict [ token → url ]\nin-memory\n重啟清空")]
    end

    subgraph DB ["SQLite  —  qr_code.db  （磁碟持久化）"]
        direction LR
        UM[("url_mappings\n──────────\ntoken  PK\noriginal_url\ncreated_at\nupdated_at\nexpires_at\nis_deleted")]
        SE[("scan_events\n──────────\nid  PK\ntoken\nscanned_at\nip_address\nuser_agent")]
    end

    %% Client → App
    Client -->|"瀏覽器開頁面"| FE
    Client -->|"建立 QR code"| RL
    Client -->|"掃描 / 點短網址"| RedirectR
    Client -->|"查詢 metadata"| InfoR
    Client -->|"修改目標網址"| UpdateR
    Client -->|"刪除"| DeleteR
    Client -->|"下載 QR 圖片"| ImageR
    Client -->|"查看掃描統計"| AnalyticsR

    %% Rate Limiter
    RL -->|"429 超額"| Client
    RL -->|pass| CreateR

    %% Create flow
    CreateR -->|"INSERT token + url"| UM
    CreateR -->|"warm cache\n（expires_at = NULL 才快取）"| Cache

    %% Redirect flow
    RedirectR -->|"1. cache hit → 302"| Client
    RedirectR -->|"2. cache miss"| UM
    UM -->|"not found → 404"| Client
    UM -->|"is_deleted / 已過期 → 410"| Client
    UM -->|"ok → warm cache + 302"| Cache
    RedirectR -->|"INSERT scan row"| SE

    %% Other flows
    InfoR --> UM
    UpdateR -->|"UPDATE url / expires_at"| UM
    UpdateR -->|"invalidate cache"| Cache
    DeleteR -->|"SET is_deleted = true"| UM
    DeleteR -->|"invalidate cache"| Cache
    ImageR --> UM
    AnalyticsR -->|"COUNT(*)"| SE
    AnalyticsR -->|"GROUP BY date"| SE
```

---

## 資料存放位置一覽

| 資料 | 存放位置 | 重啟後 |
|------|---------|--------|
| token ↔ 原始 URL | `url_mappings`（SQLite） | **保留** |
| 過期時間、刪除狀態 | `url_mappings`（SQLite） | **保留** |
| 每次掃描紀錄 | `scan_events`（SQLite） | **保留** |
| redirect 快取 | `redirect_cache` dict（記憶體） | **消失** |
| Rate limit 計數 | slowapi 記憶體 counter | **消失** |
