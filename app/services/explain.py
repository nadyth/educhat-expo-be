import json
import logging
import uuid
from collections import OrderedDict
from collections.abc import AsyncGenerator

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.document_content import DocumentContent
from app.models.file import File
from app.services import ollama

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

RERANK_SYSTEM_PROMPT = """\
You are a relevance scoring engine for a textbook search system.
Given a student's question and text chunks from a book, score each chunk's \
relevance to answering the question on a scale of 0 to 10.

Rules:
- Score 7-10: chunk directly contains information that helps answer the question.
- Score 4-6: chunk mentions related concepts but does not directly address the question.
- Score 0-3: chunk has no meaningful connection to the question.

You MUST respond with ONLY a valid JSON object mapping each chunk ID (string) \
to its integer score. Example: {"1": 8, "2": 3, "3": 9}\
"""

ANALYSIS_SYSTEM_PROMPT = """\
You are an academic content analyst. Your job is to examine book excerpts \
and extract information relevant to a student's question.

Rules:
- Only identify facts, definitions, explanations, and examples that are \
explicitly stated in the provided book excerpts.
- Do NOT add any knowledge that is not in the excerpts.
- If the excerpts contain insufficient information to answer the question, \
explicitly state what is missing.
- Be specific: cite which page the information comes from.
- Organize the relevant information logically so it can be used to construct \
a clear answer.\
"""

ANSWER_SYSTEM_PROMPT = """\
You are a study assistant for an educational textbook. Your ONLY source of \
knowledge is the book content provided below.

STRICT RULES — YOU MUST FOLLOW ALL OF THESE:
1. You may ONLY state information that is present in the provided book content \
or the analysis of that content.
2. You MAY rephrase, summarize, and explain concepts from the book in your own \
words for clarity. This is encouraged.
3. You must NOT introduce any information, facts, examples, analogies, or \
explanations that are NOT present in the book content.
4. If the book content does not contain enough information to fully answer the \
question, you MUST explicitly say so and explain what information is missing.
5. Do NOT use your general world knowledge to fill in gaps. If the book is \
silent on a point, you are silent on that point.
6. When making connections between concepts, only connect ideas that BOTH appear \
in the book content.
7. Respond in the same language as the book content.
8. Structure your answer clearly for a student: use headings, bullet points, \
or numbered steps where appropriate.

OUTPUT FORMAT — follow these exactly so the frontend renders correctly:
- Use **double asterisks** for bold, never __double underscores__.
- Use *single asterisk* for italic, never _single underscore_.
- Use `backticks` for inline code or technical terms.
- ALWAYS close every formatting marker. Never leave an opening ** or * \
without its matching closing marker.
- Never nest formatting (e.g., no **bold *italic* bold**).
- Avoid tables, HTML, and complex markdown — stick to headings (#), \
bullet lists (-), numbered lists (1.), and the three inline styles above.

Remember: you are an EXPLAINER of the book, not an independent expert. Every \
sentence you write must be traceable to the book content.\
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _fallback_rerank(rows: list, top_n: int = 3) -> list[int]:
    """Fallback: deduplicate by page using cosine distance, return top page numbers."""
    best_per_page: OrderedDict[int, float] = OrderedDict()
    for row in rows:
        pn = row.page_number
        if pn not in best_per_page or row.distance < best_per_page[pn]:
            best_per_page[pn] = row.distance
    return sorted(best_per_page, key=best_per_page.get)[:top_n]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def explain_concept(
    file_id: uuid.UUID,
    question: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Orchestrate the explain-concept agent, yielding SSE events."""

    # --- Step 1: Embed question ---
    yield _sse("step", {"step": "embedding", "label": "Understanding your question..."})

    embeddings = await ollama.embed([question])
    query_vector = embeddings[0]

    # --- Step 2: Vector search ---
    yield _sse("step", {"step": "searching", "label": "Searching in book..."})

    search_sql = text(
        """
        SELECT content_id, page_number, page_label, chunk_index, content,
               content_vector <=> CAST(:vec AS vector) AS distance
        FROM document_contents
        WHERE file_id = :fid
        ORDER BY content_vector <=> CAST(:vec AS vector)
        LIMIT 10
        """
    )
    result = await db.execute(
        search_sql, {"vec": str(query_vector), "fid": str(file_id)}
    )
    rows = result.fetchall()

    if not rows:
        yield _sse("step", {"step": "no_results", "label": "No relevant content found"})
        yield _sse(
            "token",
            {"text": "I couldn't find any relevant content in this book for your question."},
        )
        yield _sse("done", {})
        return

    # --- Step 3: LLM Reranking ---
    yield _sse("step", {"step": "reranking", "label": "Ranking best results..."})

    # Build reranking prompt
    chunks_text = "\n\n".join(
        f"[{i+1}] (page {row.page_label}):\n{row.content}"
        for i, row in enumerate(rows)
    )
    rerank_prompt = (
        f"Question: {question}\n\nChunks:\n{chunks_text}\n\n"
        "Respond with the JSON scores now."
    )

    top_page_numbers: list[int]
    try:
        rerank_result = await ollama.generate({
            "model": settings.ollama_chat_model,
            "system": RERANK_SYSTEM_PROMPT,
            "prompt": rerank_prompt,
            "format": "json",
        })
        scores_raw = json.loads(rerank_result["response"])
        # Attach scores to rows
        scored_rows = []
        for i, row in enumerate(rows):
            score = scores_raw.get(str(i + 1), 0)
            try:
                score = int(score)
            except (ValueError, TypeError):
                score = 0
            scored_rows.append((row, score))

        # Group by page, take max score per page
        page_scores: dict[int, int] = {}
        for row, score in scored_rows:
            pn = row.page_number
            if pn not in page_scores or score > page_scores[pn]:
                page_scores[pn] = score

        top_page_numbers = sorted(page_scores, key=page_scores.get, reverse=True)[:3]
    except (json.JSONDecodeError, KeyError, Exception) as exc:
        logger.warning("LLM reranking failed, falling back to distance: %s", exc)
        top_page_numbers = _fallback_rerank(rows)

    # --- Step 4: Expand context (page-1, page, page+1) ---
    yield _sse("step", {"step": "expanding", "label": "Looking at nearby pages..."})

    page_numbers: set[int] = set()
    for pn in top_page_numbers:
        if pn > 1:
            page_numbers.add(pn - 1)
        page_numbers.add(pn)
        page_numbers.add(pn + 1)

    file_result = await db.execute(select(File.pages_total).where(File.id == file_id))
    pages_total = file_result.scalar_one()
    page_numbers = {p for p in page_numbers if 1 <= p <= pages_total}

    expand_result = await db.execute(
        select(DocumentContent)
        .where(
            DocumentContent.file_id == file_id,
            DocumentContent.page_number.in_(page_numbers),
        )
        .order_by(DocumentContent.page_number, DocumentContent.chunk_index)
    )
    expanded_rows = expand_result.scalars().all()

    # Group by page, build source list
    pages_content: dict[int, list[dict]] = {}
    for row in expanded_rows:
        pn = row.page_number
        pages_content.setdefault(pn, []).append(
            {"page_label": row.page_label, "content": row.content}
        )

    source_pages: list[dict] = []
    for pn in sorted(pages_content):
        label = pages_content[pn][0]["page_label"]
        source_pages.append({"page_number": pn, "page_label": label})

    yield _sse("sources", {"pages": source_pages})

    # Build context text grouped by page
    context_parts: list[str] = []
    for pn in sorted(pages_content):
        chunks = pages_content[pn]
        label = chunks[0]["page_label"]
        page_text = "\n".join(c["content"] for c in chunks)
        context_parts.append(f"--- Page {label} ---\n{page_text}")

    context_text = "\n\n".join(context_parts)

    # --- Step 5: Analysis ---
    yield _sse("step", {"step": "analyzing", "label": "Analyzing relevant content..."})

    analysis_output = ""
    analysis_prompt = (
        f"Student's question: {question}\n\n"
        f"Book excerpts:\n{context_text}\n\n"
        "Please analyze these excerpts and provide:\n"
        "1. RELEVANT EXCERPTS: Which pages contain information relevant to the question\n"
        "2. KEY FACTS: The specific facts, definitions, and explanations from these "
        "excerpts that address the question, citing the source page for each\n"
        "3. GAPS: Any aspects of the question that the excerpts do not address"
    )

    try:
        analysis_output = await ollama.chat([
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": analysis_prompt},
        ])
    except Exception as exc:
        logger.warning("Analysis step failed, proceeding with raw context: %s", exc)

    # --- Step 6: Generate answer ---
    yield _sse("step", {"step": "generating", "label": "Generating answer..."})

    if analysis_output:
        user_content = (
            f"Question: {question}\n\n"
            f"Analysis of relevant book content:\n{analysis_output}\n\n"
            f"Full book excerpts for verification:\n{context_text}"
        )
    else:
        user_content = (
            f"Based on these excerpts from the book:\n\n{context_text}\n\n"
            f"Question: {question}"
        )

    messages = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    async for token in ollama.stream_chat(messages):
        yield _sse("token", {"text": token})

    yield _sse("done", {})