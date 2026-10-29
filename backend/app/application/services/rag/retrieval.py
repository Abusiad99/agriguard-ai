"""
Hybrid retriever over knowledge chunks.

* Lexical: Okapi BM25 (k1=1.5, b=0.75) over the bilingual tokenizer in text.py — always
  available, deterministic, no external service.
* Semantic (optional): cosine similarity between a query embedding and stored chunk
  embeddings, when both exist and come from the same embedding model.
* Fusion: reciprocal-rank fusion (RRF, k=60) of the two rankings, plus a small boost
  for chunks whose document metadata matches the crop/disease in context.

A chunk is only returned if it contains enough of the question's terms (term
coverage — unlike a raw BM25 floor this does not depend on corpus size) or is highly
similar semantically; otherwise the assistant reports that no relevant source was
found instead of padding the prompt with unrelated text.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from app.application.services.rag.text import tokenize


@dataclass
class IndexedChunk:
    chunk_id: str
    document_id: str
    text: str
    section: Optional[str]
    title: str
    organization: str
    source_url: Optional[str]
    source_type: str
    language: str
    published_date: Optional[str]
    revised_date: Optional[str]
    crops: List[str] = field(default_factory=list)
    diseases: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None
    embedding_model: Optional[str] = None


@dataclass
class RetrievedChunk:
    chunk: IndexedChunk
    score: float
    bm25: float
    cosine: Optional[float]


class HybridIndex:
    def __init__(self, chunks: Sequence[IndexedChunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = list(chunks)
        self.k1, self.b = k1, b
        self._tf: List[Counter] = []
        self._len: List[int] = []
        df: Counter = Counter()
        for c in self.chunks:
            toks = tokenize(" ".join(filter(None, [c.title, c.section or "", c.text])))
            tf = Counter(toks)
            self._tf.append(tf)
            self._len.append(len(toks))
            df.update(tf.keys())
        n = len(self.chunks)
        self._avgdl = (sum(self._len) / n) if n else 0.0
        self._idf: Dict[str, float] = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def __len__(self) -> int:
        return len(self.chunks)

    def term_coverage(self, query: str) -> List[float]:
        """Fraction of distinct query terms that occur in each chunk."""
        q = set(tokenize(query))
        if not q:
            return [0.0] * len(self.chunks)
        return [len(q & tf.keys()) / len(q) for tf in self._tf]

    def bm25_scores(self, query: str) -> List[float]:
        q = [t for t in tokenize(query) if t in self._idf]
        if not q or not self.chunks:
            return [0.0] * len(self.chunks)
        scores = []
        for tf, dl in zip(self._tf, self._len):
            s = 0.0
            for t in q:
                f = tf.get(t)
                if not f:
                    continue
                s += self._idf[t] * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1)))
            scores.append(s)
        return scores

    def search(self, query: str, top_k: int = 5, query_embedding: Optional[List[float]] = None,
               embedding_model: Optional[str] = None, crops: Sequence[str] = (), diseases: Sequence[str] = (),
               min_coverage: float = 0.3, min_matched_terms: int = 3,
               min_cosine: float = 0.55) -> List[RetrievedChunk]:
        if not self.chunks:
            return []
        bm25 = self.bm25_scores(query)
        coverage = self.term_coverage(query)
        n_query_terms = len(set(tokenize(query)))
        cosine: List[Optional[float]] = [None] * len(self.chunks)
        if query_embedding:
            for i, c in enumerate(self.chunks):
                if c.embedding and c.embedding_model == embedding_model and len(c.embedding) == len(query_embedding):
                    cosine[i] = _cos(query_embedding, c.embedding)

        lexical_rank = {i: r for r, i in enumerate(sorted(range(len(bm25)), key=lambda i: -bm25[i])) if bm25[i] > 0}
        semantic_rank = {i: r for r, i in enumerate(sorted((i for i, v in enumerate(cosine) if v is not None),
                                                            key=lambda i: -cosine[i]))}
        crops_l = {c.lower() for c in crops if c}
        diseases_l = {d.lower() for d in diseases if d}
        fused = []
        for i, c in enumerate(self.chunks):
            matched = round(coverage[i] * n_query_terms)
            lexical_ok = bm25[i] > 0 and (coverage[i] >= min_coverage or matched >= min_matched_terms)
            relevant = lexical_ok or (cosine[i] is not None and cosine[i] >= min_cosine)
            if not relevant:
                continue
            score = 0.0
            if i in lexical_rank:
                score += 1.0 / (60 + lexical_rank[i])
            if i in semantic_rank:
                score += 1.0 / (60 + semantic_rank[i])
            if crops_l and crops_l & {x.lower() for x in c.crops}:
                score *= 1.15
            if diseases_l and diseases_l & {x.lower() for x in c.diseases}:
                score *= 1.25
            fused.append(RetrievedChunk(chunk=c, score=score, bm25=bm25[i], cosine=cosine[i]))
        fused.sort(key=lambda r: -r.score)

        # At most 2 chunks per document so one long document cannot crowd out others.
        out, per_doc = [], Counter()
        for r in fused:
            if per_doc[r.chunk.document_id] >= 2:
                continue
            per_doc[r.chunk.document_id] += 1
            out.append(r)
            if len(out) >= top_k:
                break
        return out


def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
