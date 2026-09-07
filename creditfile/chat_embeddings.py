"""Optional, local-only ONNX hybrid retrieval. Never downloads a model."""

from functools import lru_cache
from pathlib import Path
from .model import ModelError
from .schemas import Block


@lru_cache(maxsize=1)
def encoder(directory: str):
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        path = Path(directory)
        if not (path / "model_quantized.onnx").is_file() or not (path / "tokenizer.json").is_file():
            raise ValueError("Missing local files")
        tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=128)
        tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(
            str(path / "model_quantized.onnx"), options, providers=["CPUExecutionProvider"]
        )
        return tokenizer, session
    except Exception as exc:
        # ORT model/graph failures use extension exception classes. This scope
        # only initializes the optional runtime; it never handles user facts.
        raise ModelError(
            "Η προαιρετική αναζήτηση embeddings δεν είναι διαθέσιμη. Εγκατάστησε τις προαιρετικές εξαρτήσεις και το τοπικό μοντέλο ή όρισε CHAT_RETRIEVER=bm25."
        ) from exc


def encode(directory: str, texts: list[str]):
    import numpy as np

    tokenizer, session = encoder(directory)
    enc = tokenizer.encode_batch(texts)
    arrays = dict(
        input_ids=np.array([e.ids for e in enc], dtype=np.int64),
        attention_mask=np.array([e.attention_mask for e in enc], dtype=np.int64),
        token_type_ids=np.array([e.type_ids for e in enc], dtype=np.int64),
    )
    output = session.run(None, {i.name: arrays[i.name] for i in session.get_inputs()})[0]
    mask = arrays["attention_mask"][..., None]
    vectors = (output * mask).sum(1) / mask.sum(1)
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)


@lru_cache(maxsize=8)
def indexed(directory: str, case_id: str, texts: tuple[str, ...]):
    import numpy as np

    return np.vstack([encode(directory, list(texts[i : i + 4])) for i in range(0, len(texts), 4)])


def hybrid_select(
    case_id: str, blocks: list[Block], query: str, baseline: list[Block], directory: str, top_k: int
) -> list[Block]:
    import numpy as np

    # Filter before encoding: neither another case nor its vectors can participate.
    allowed = [b for b in blocks if b.case_id == case_id]
    if not allowed:
        return []
    by_id = {b.block_id: b for b in allowed}
    directory = str(Path(directory).resolve())
    vectors = indexed(directory, case_id, tuple(b.text for b in allowed))
    scores = vectors @ encode(directory, [query])[0]
    ranks = {
        b.block_id: 1 / (61 + i)
        for i, b in enumerate(baseline)
        if b.block_id in by_id and b.case_id == case_id
    }
    for i, index in enumerate(np.argsort(-scores)):
        ident = allowed[index].block_id
        ranks[ident] = ranks.get(ident, 0) + 1 / (61 + i)
    pages = []
    for ident in sorted(ranks, key=ranks.get, reverse=True):
        b = by_id[ident]
        page = (b.document_id, b.page)
        if page not in pages:
            pages.append(page)
        if len(pages) == top_k:
            break
    return [b for page in pages for b in allowed if (b.document_id, b.page) == page][: top_k * 6]
