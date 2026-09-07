"""Conservative lexical gate and additive, case-scoped semantic retrieval."""

from .pipeline import tokens

STOP = set(
    "ποιο ποιος ποια ποιες ποιους ποιας ποιων ποσο ποσα τι πως που ειναι η ο το τα τις της την τον των του σε στο στη στην στον στα απο για με και να εχει εχουν εχω υπαρχει υπαρχουν θελει μπορει μου μας αυτο αυτη αυτα αυτος ενας μια ενα please what which is are the a an of for to in does".split()
)


def lexical_coverage(question, baseline):
    # An interpretable heuristic, not an answer-confidence probability.
    terms = set(tokens(question)) - STOP
    if not terms or not baseline:
        return 0.0
    return max(len(terms & set(tokens(b.text))) / len(terms) for b in baseline)


def supplement(case_id, blocks, question, baseline, directory, top_k):
    from .chat_embeddings import hybrid_select

    allowed = [b for b in blocks if b.case_id == case_id]
    by_id = {b.block_id: b for b in allowed}
    baseline = [b for b in baseline if b.case_id == case_id and b.block_id in by_id]
    coverage = lexical_coverage(question, baseline)
    info = dict(
        lexical_coverage=round(coverage, 3),
        embedding_attempted=False,
        embedding_added=0,
        fallback_reason=None,
    )
    if coverage >= 0.8:
        return baseline, info
    info.update(
        embedding_attempted=True,
        fallback_reason="empty_bm25" if not baseline else "weak_lexical_coverage",
    )
    try:
        candidates = hybrid_select(case_id, allowed, question, baseline, directory, top_k)
    except Exception as exc:
        # Optional local runtime failure must not remove working lexical context.
        info["embedding_error"] = type(exc).__name__
        return baseline, info
    result = list(baseline)
    seen = {b.block_id for b in baseline}
    pages = list(
        dict.fromkeys(
            (b.document_id, b.page)
            for b in candidates
            if b.case_id == case_id and b.block_id in by_id
        )
    )
    for page in pages[:top_k]:
        additions = [
            b for b in allowed if (b.document_id, b.page) == page and b.block_id not in seen
        ]
        # Append entire pages; original BM25 tables and anchors keep their order.
        if len(result) + len(additions) > len(baseline) + top_k * 6:
            continue
        result.extend(additions)
        seen.update(b.block_id for b in additions)
    info["embedding_added"] = len(result) - len(baseline)
    return result, info
