"""
BM25 / Vector / Hybrid / Hybrid+Rewrite 四欄對照測試腳本
使用前：uvicorn app.main:app --port 8000
執行方式：python test_queries.py
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8000"

QUERIES = [
    ("1A", "中英同義",          "退款需要幾天"),
    ("1B", "中英同義",          "refund how many days"),
    ("2A", "action request",    "cancel my order"),
    ("2B", "BM25 synonym miss", "revoke purchase"),
    ("3A", "語意",              "I want my money back"),
    ("3B", "action request",    "request a return after delivery"),
    ("4A", "false positive",    "change my password"),
    ("4B", "跨主題",            "shipping timeline"),
    ("5A", "exact keyword",     "non-refundable items"),
    ("5B", "語意改寫",          "what cannot be returned"),
]


def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fmt_answer(text: str) -> str:
    if "cannot confirm" in text.lower():
        return "❌ 拒答"
    return text[:80].replace("\n", " ") + ("…" if len(text) > 80 else "")


def score_label(sources: list, threshold_applied: bool, strategy: str) -> str:
    if threshold_applied:
        return "threshold"
    if not sources:
        return "—"
    s = sources[0]
    if strategy == "bm25":
        return f"{s['score']:.3f}"
    elif strategy == "hybrid":
        return f"RRF={s['score']:.4f}"
    else:
        return f"L2={s['score']:.4f}"


def win(answer: str) -> str:
    return "✅" if "cannot confirm" not in answer.lower() and answer != "—" else "❌"


def main():
    print("=== POST /index ===")
    try:
        idx = post("/index", {})
        print(f"  files={idx['files_indexed']}  sections={idx['sections_indexed']}  chunks={idx['chunks_indexed']}\n")
    except urllib.error.URLError as e:
        print(f"  ERROR: {e}\n  Server is not running on port 8000?\n")
        sys.exit(1)

    # ── Section 1: 3-column table (original comparison) ─────────────────────
    header = (
        f"{'#':<4} {'類型':<18} {'Query':<38} "
        f"{'BM25':^12} {'BM25 Answer':<40} "
        f"{'Vector':^12} {'Vector Answer':<40} "
        f"{'Hybrid RRF':^12} {'Hybrid Answer'}"
    )
    print(header)
    print("-" * len(header))

    compare_cache: dict[str, dict] = {}
    for num, category, query in QUERIES:
        try:
            r = post("/compare", {"query": query})
        except Exception as e:
            print(f"{num:<4} ERROR: {e}")
            continue

        compare_cache[num] = r
        bm25   = r["bm25"]
        vec    = r["vector"]
        hybrid = r.get("hybrid") or {}

        bm25_score_str   = score_label(bm25.get("sources", []),  bm25.get("threshold_applied", False),  "bm25")
        vec_score_str    = score_label(vec.get("sources", []),   vec.get("threshold_applied", False),   "vector")
        hybrid_score_str = score_label(hybrid.get("sources", []), hybrid.get("threshold_applied", True), "hybrid")

        print(
            f"{num:<4} {category:<18} {query:<38} "
            f"{bm25_score_str:<12} {fmt_answer(bm25.get('answer','—')):<40} "
            f"{vec_score_str:<12} {fmt_answer(vec.get('answer','—')):<40} "
            f"{hybrid_score_str:<12} {fmt_answer(hybrid.get('answer','—'))}"
        )

    # ── Section 2: Hybrid + Query Rewrite showcase ───────────────────────────
    print("\n\n=== Hybrid + Query Rewrite Showcase ===")
    print(f"{'#':<4} {'Query':<38} {'Rewritten Query':<38} {'RRF':^12} {'△':^4} {'Answer (truncated)'}")
    print("-" * 130)

    for num, category, query in QUERIES:
        r = compare_cache.get(num, {})
        hr = r.get("hybrid_rewrite") or {}
        hybrid = r.get("hybrid") or {}

        rw_query    = hr.get("rewritten_query") or "—"
        rw_score    = score_label(hr.get("sources", []), hr.get("threshold_applied", True), "hybrid")
        rw_ans      = hr.get("answer", "—")
        hybrid_ans  = hybrid.get("answer", "—")

        # △ = improved over hybrid-without-rewrite?
        improved = win(rw_ans) == "✅" and win(hybrid_ans) == "❌"
        same     = win(rw_ans) == win(hybrid_ans)
        delta    = "▲" if improved else ("=" if same else "▼")

        print(
            f"{num:<4} {query:<38} {rw_query:<38} {rw_score:<12} {delta:<4} {fmt_answer(rw_ans)}"
        )

    # ── Section 3: Score summary ─────────────────────────────────────────────
    print("\n\n=== Score Summary ===")
    counts = {"bm25": 0, "vector": 0, "hybrid": 0, "hybrid+rewrite": 0}
    for num, _, _ in QUERIES:
        r = compare_cache.get(num, {})
        for key, label in [("bm25","bm25"), ("vector","vector"), ("hybrid","hybrid"), ("hybrid_rewrite","hybrid+rewrite")]:
            ans = (r.get(key) or {}).get("answer", "")
            if win(ans) == "✅":
                counts[label] += 1
    for label, n in counts.items():
        bar = "█" * n + "░" * (10 - n)
        print(f"  {label:<18} {bar}  {n}/10")

    print("\n完成。")


if __name__ == "__main__":
    main()
