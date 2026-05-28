from pydantic import BaseModel


class IndexResponse(BaseModel):
    files_indexed: int
    sections_indexed: int
    chunks_indexed: int = 0


class ChatRequest(BaseModel):
    query: str
    score_threshold: float = 0.5
    session_id: str | None = None
    strategy: str = "bm25"  # "bm25" or "vector"


class SourceInfo(BaseModel):
    source: str
    heading: str
    score: float
    content: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]
    threshold_applied: bool = False
    session_id: str
    strategy: str = "bm25"
    rewritten_query: str | None = None


class CompareResult(BaseModel):
    answer: str
    sources: list[SourceInfo]
    threshold_applied: bool = False
    strategy: str
    rewritten_query: str | None = None


class CompareResponse(BaseModel):
    query: str
    bm25: CompareResult
    vector: CompareResult
    hybrid: CompareResult | None = None
    hybrid_rewrite: CompareResult | None = None
