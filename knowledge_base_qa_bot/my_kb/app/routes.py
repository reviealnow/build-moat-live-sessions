import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .indexer import build_index as bm25_build_index
from . import indexer_vector
from .retrieval import query as bm25_query, query_stream
from . import retrieval_vector, retrieval_hybrid
from .schemas import (
    ChatRequest, ChatResponse, CompareResponse, CompareResult, IndexResponse
)

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/index", response_model=IndexResponse)
def index_docs():
    files_count, sections_count = bm25_build_index()
    _, chunks_count = indexer_vector.build_index()
    return IndexResponse(
        files_indexed=files_count,
        sections_indexed=sections_count,
        chunks_indexed=chunks_count,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if req.strategy == "vector":
        result = retrieval_vector.query(req.query, score_threshold=req.score_threshold)
        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            threshold_applied=result["threshold_applied"],
            session_id=str(uuid.uuid4()),
            strategy="vector",
        )
    if req.strategy == "hybrid":
        result = retrieval_hybrid.query(req.query, session_id=req.session_id)
        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            threshold_applied=result["threshold_applied"],
            session_id=result["session_id"],
            strategy="hybrid",
        )
    if req.strategy == "hybrid+rewrite":
        result = retrieval_hybrid.query(req.query, session_id=req.session_id, use_rewrite=True)
        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            threshold_applied=result["threshold_applied"],
            session_id=result["session_id"],
            strategy="hybrid+rewrite",
            rewritten_query=result.get("rewritten_query"),
        )
    return bm25_query(req.query, score_threshold=req.score_threshold, session_id=req.session_id)


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    return StreamingResponse(
        query_stream(req.query, score_threshold=req.score_threshold, session_id=req.session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/compare", response_model=CompareResponse)
def compare(req: ChatRequest):
    bm25_result = bm25_query(req.query, score_threshold=req.score_threshold)
    vector_result = retrieval_vector.query(req.query)
    hybrid_result = retrieval_hybrid.query(req.query)
    hybrid_rw_result = retrieval_hybrid.query(req.query, use_rewrite=True)

    return CompareResponse(
        query=req.query,
        bm25=CompareResult(
            answer=bm25_result["answer"],
            sources=bm25_result.get("sources", []),
            threshold_applied=bm25_result.get("threshold_applied", False),
            strategy="bm25",
        ),
        vector=CompareResult(
            answer=vector_result["answer"],
            sources=vector_result.get("sources", []),
            threshold_applied=vector_result.get("threshold_applied", False),
            strategy="vector",
        ),
        hybrid=CompareResult(
            answer=hybrid_result["answer"],
            sources=hybrid_result.get("sources", []),
            threshold_applied=hybrid_result.get("threshold_applied", False),
            strategy="hybrid",
        ),
        hybrid_rewrite=CompareResult(
            answer=hybrid_rw_result["answer"],
            sources=hybrid_rw_result.get("sources", []),
            threshold_applied=hybrid_rw_result.get("threshold_applied", False),
            strategy="hybrid+rewrite",
            rewritten_query=hybrid_rw_result.get("rewritten_query"),
        ),
    )
