"""
Hybrid retrieval: Reciprocal Rank Fusion (RRF) over BM25 + Vector results.

RRF formula: score(d) = Σ  1 / (k + rank_i(d))
k=60 is the standard smoothing constant from the original RRF paper.

Rejection rule: the top-ranked fused candidate must have appeared in at least
one system with a meaningful signal:
  - BM25 returned it (score > 0 after synonym expansion), OR
  - Vector L2 distance < _VECTOR_MAX_L2
If neither holds, the query is out-of-scope and we refuse.
"""
from __future__ import annotations

import os

from . import indexer as bm25_indexer
from . import indexer_vector
from . import query_rewrite as _qr
from .retrieval import SYSTEM_PROMPT, _get_client, _get_session, _save_turn

_RRF_K = 60
_VECTOR_MAX_L2 = 1.2
_RETRIEVE_K = 5   # candidates fetched per system before fusion
_ANSWER_K = 3     # top chunks passed to LLM


def _rrf_fuse(
    bm25_results: list,    # [(Section, bm25_score)]  higher = better
    vector_results: list,  # [(Document, l2_distance)] lower  = better
) -> list[tuple[str, float, object | None, object | None]]:
    """Return [(source_id, rrf_score, section|None, doc|None)] sorted desc."""
    rrf: dict[str, float] = {}
    bm25_map: dict[str, object] = {}
    vec_map: dict[str, object] = {}

    for rank, (section, _) in enumerate(bm25_results):
        sid = section.id
        rrf[sid] = rrf.get(sid, 0.0) + 1.0 / (_RRF_K + rank + 1)
        bm25_map[sid] = section

    seen_vec: set[str] = set()
    for rank, (doc, _) in enumerate(vector_results):
        sid = doc.metadata.get("source", "")
        if not sid or sid in seen_vec:
            continue
        seen_vec.add(sid)
        rrf[sid] = rrf.get(sid, 0.0) + 1.0 / (_RRF_K + rank + 1)
        vec_map[sid] = doc

    fused = sorted(rrf.items(), key=lambda x: x[1], reverse=True)
    return [(sid, sc, bm25_map.get(sid), vec_map.get(sid)) for sid, sc in fused]


def _quality_ok(
    fused: list,
    bm25_results: list,
    vector_results: list,
) -> bool:
    if not fused:
        return False
    top_sid = fused[0][0]
    bm25_ids = {s.id for s, _ in bm25_results}
    vec_ids_good = {
        doc.metadata.get("source", "")
        for doc, dist in vector_results
        if dist < _VECTOR_MAX_L2
    }
    return top_sid in bm25_ids or top_sid in vec_ids_good


def _build_prompt(query: str, top: list, rewritten: str | None = None) -> str:
    blocks = []
    for sid, rrf_score, section, doc in top:
        if section is not None:
            heading = " > ".join(section.heading_path)
            content = section.content
        elif doc is not None:
            heading = doc.metadata.get("heading", sid)
            content = doc.page_content
        else:
            continue
        blocks.append(
            f"[Source: {sid}] [RRF: {rrf_score:.4f}]\n"
            f"{heading}\n\n{content}"
        )
    context = "\n\n---\n\n".join(blocks)
    if rewritten and rewritten.lower() != query.lower():
        question_block = f"{query}\n[Interpreted as: {rewritten}]"
    else:
        question_block = query
    return f"CONTEXT:\n{context}\n\nQUESTION:\n{question_block}"


def query(
    question: str,
    session_id: str | None = None,
    use_rewrite: bool = False,
) -> dict:
    sid, history = _get_session(session_id)

    if not bm25_indexer.sections:
        return {
            "answer": "The knowledge base has not been indexed yet. Call POST /index first.",
            "sources": [],
            "threshold_applied": False,
            "strategy": "hybrid" if not use_rewrite else "hybrid+rewrite",
            "session_id": sid,
            "rewritten_query": None,
        }

    rewritten = _qr.rewrite(question) if use_rewrite else None
    retrieval_query = rewritten if rewritten else question

    bm25_results = bm25_indexer.search(retrieval_query, k=_RETRIEVE_K)
    vector_results = indexer_vector.search(retrieval_query, k=_RETRIEVE_K) if indexer_vector.vectorstore else []

    fused = _rrf_fuse(bm25_results, vector_results)

    strategy_label = "hybrid+rewrite" if use_rewrite else "hybrid"

    if not _quality_ok(fused, bm25_results, vector_results):
        return {
            "answer": "I cannot confirm from the knowledge base.",
            "sources": [],
            "threshold_applied": True,
            "strategy": strategy_label,
            "session_id": sid,
            "rewritten_query": rewritten,
        }

    top = fused[:_ANSWER_K]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": _build_prompt(question, top, rewritten)},
    ]

    response = _get_client().chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        timeout=20,
    )
    answer = response.choices[0].message.content
    _save_turn(sid, question, answer)

    sources = [
        {
            "source": sid_,
            "heading": (
                " > ".join(sec.heading_path) if sec
                else (doc.metadata.get("heading", sid_) if doc else sid_)
            ),
            "score": round(rrf_score, 4),
            "content": (
                sec.content[:240] if sec
                else (doc.page_content[:240] if doc else "")
            ),
        }
        for sid_, rrf_score, sec, doc in top
    ]

    return {
        "answer": answer,
        "sources": sources,
        "threshold_applied": False,
        "strategy": strategy_label,
        "session_id": sid,
        "rewritten_query": rewritten,
    }
