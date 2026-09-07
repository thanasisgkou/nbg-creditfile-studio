import os
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    provider: str = "openrouter"
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "google/gemini-2.5-flash"
    endpoint: str = "google-ai-studio"
    prompt_version: str = "creditfile-v2.3-realistic"
    reasoning_enabled: bool = False
    retries: int = 2
    concurrency: int = 2
    execution_mode: str = "live"
    temperature: float = 0
    num_ctx: int = 65536
    num_predict: int = 8192
    timeout: int = 120
    top_k: int = 6
    chunk_chars: int = 900
    overlap: int = 100
    data_dir: Path = ROOT / "data"
    max_mb: int = 10
    max_pages: int = 10
    max_documents: int = 4
    chat_retriever: str = "bm25"
    chat_query_rewrite: bool = False
    embedding_model_dir: Path = ROOT / "models" / "embeddings" / "multilingual-minilm"

    def __post_init__(self):
        if self.chat_retriever not in {"bm25", "hybrid", "bm25_fallback"}:
            raise ValueError("Το CHAT_RETRIEVER πρέπει να είναι bm25, hybrid ή bm25_fallback.")
        if not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ValueError("Μη έγκυρη θερμοκρασία μοντέλου (0–2).")
        url = urlparse(self.base_url)
        if self.provider not in {"openrouter", "ollama", "openai-compatible"}:
            raise ValueError("Μη υποστηριζόμενος LLM_PROVIDER.")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Το base URL δεν επιτρέπεται να περιέχει διαπιστευτήρια ή query.")
        if (
            self.provider == "openrouter"
            and self.base_url.rstrip("/") != "https://openrouter.ai/api/v1"
        ):
            raise ValueError(
                "Το OpenRouter key αποστέλλεται μόνο στο https://openrouter.ai/api/v1."
            )
        if self.provider == "ollama" and (
            url.scheme != "http"
            or url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or url.path not in {"", "/"}
        ):
            raise ValueError("Το Ollama πρέπει να χρησιμοποιεί HTTP μόνο στο loopback.")
        if self.provider == "openai-compatible" and not (
            url.scheme == "https"
            or url.scheme == "http"
            and url.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError("Το εγκεκριμένο endpoint απαιτεί HTTPS ή τοπικό HTTP.")
        if (
            not 0 <= self.retries <= 2
            or not 1 <= self.concurrency <= 2
            or self.execution_mode not in {"live", "replay"}
        ):
            raise ValueError("Μη έγκυρα όρια κλήσεων ή execution mode.")
        if (
            min(
                self.num_ctx,
                self.num_predict,
                self.timeout,
                self.top_k,
                self.chunk_chars,
                self.max_mb,
                self.max_pages,
                self.max_documents,
            )
            <= 0
            or not 0 <= self.overlap < self.chunk_chars
        ):
            raise ValueError("Μη έγκυρα όρια ρυθμίσεων.")

    @classmethod
    def load(cls):
        environment = os.environ
        provider = environment.get("LLM_PROVIDER", "openrouter")
        prefix = {"openrouter": "OPENROUTER", "ollama": "OLLAMA", "openai-compatible": "LLM"}.get(
            provider, "LLM"
        )
        mapping = {
            "base_url": (prefix + "_BASE_URL", str),
            "model": (prefix + "_MODEL", str),
            "temperature": ("LLM_TEMPERATURE", float),
            "num_ctx": ("LLM_NUM_CTX", int),
            "num_predict": ("LLM_NUM_PREDICT", int),
            "timeout": ("LLM_TIMEOUT_SECONDS", int),
            "top_k": ("RETRIEVAL_TOP_K", int),
            "chunk_chars": ("CHUNK_CHARS", int),
            "overlap": ("CHUNK_OVERLAP_CHARS", int),
            "data_dir": ("DATA_DIR", Path),
            "max_mb": ("MAX_PDF_MB", int),
            "max_pages": ("MAX_PDF_PAGES", int),
            "max_documents": ("MAX_CASE_DOCUMENTS", int),
            "endpoint": ("OPENROUTER_ENDPOINT", str),
            "retries": ("LLM_RETRIES", int),
            "concurrency": ("LLM_CONCURRENCY", int),
            "execution_mode": ("LLM_EXECUTION_MODE", str),
            "reasoning_enabled": ("LLM_REASONING_ENABLED", lambda v: v.lower() == "true"),
        }
        values = {
            key: cast(environment[env])
            for key, (env, cast) in mapping.items()
            if environment.get(env) is not None
        }
        values["provider"] = provider
        values["chat_retriever"] = environment.get("CHAT_RETRIEVER", "bm25")
        values["chat_query_rewrite"] = (
            environment.get("CHAT_QUERY_REWRITE", "false").lower() == "true"
        )
        if environment.get("CHAT_EMBEDDING_MODEL_DIR"):
            embedding_path = Path(environment["CHAT_EMBEDDING_MODEL_DIR"])
            values["embedding_model_dir"] = (
                embedding_path if embedding_path.is_absolute() else ROOT / embedding_path
            )
        if provider == "ollama":
            values.setdefault("base_url", "http://127.0.0.1:11434")
            values.setdefault("model", "qwen3:8b")
        if "data_dir" in values and not values["data_dir"].is_absolute():
            values["data_dir"] = ROOT / values["data_dir"]
        return cls(**values)


def api_key(provider):
    """Backend only; deliberately excluded from Settings, repr and run metadata."""
    name = "OPENROUTER_API_KEY" if provider == "openrouter" else "LLM_API_KEY"
    return os.environ.get(name) or ""
