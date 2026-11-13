"""Embeddings locales (6.4): fastembed con paraphrase-multilingual-MiniLM-L12-v2 (Apache-2.0, 384 dimensiones).

El modelo está dentro de la imagen worker-ai (`EMBEDDINGS_HOME`) y nunca se descarga al ejecutar. Se carga una vez por
proceso. Los vectores salen normalizados.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from core.errors import ErrorCode, ToolError
from core.settings import Settings

DIM = 384
_LOCK = threading.Lock()
_MODELS: dict[str, object] = {}


def model_dir(settings: Settings) -> Path:
    return Path(settings.EMBEDDINGS_HOME) / settings.EMBEDDINGS_MODEL.rsplit("/", 1)[-1]


def _model(settings: Settings, threads: int):
    key = str(model_dir(settings))
    with _LOCK:
        if key not in _MODELS:
            path = model_dir(settings)
            if not (path / "model_optimized.onnx").is_file():
                raise ToolError(ErrorCode.ENGINE_FAILED, f"falta el modelo de embeddings en {path}")
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from fastembed import TextEmbedding

            _MODELS[key] = TextEmbedding(settings.EMBEDDINGS_MODEL, specific_model_path=str(path), threads=max(1, threads))
        return _MODELS[key]


def embed(settings: Settings, texts: list[str], threads: int = 1, batch_size: int = 16) -> list[list[float]]:
    """Lotes de 16: el pico de memoria se queda en unos 0,7 GB por proceso (con 32 llega a 0,9, D-128)."""
    import numpy as np

    if not texts:
        return []
    vectors = np.array(list(_model(settings, threads).embed(texts, batch_size=batch_size)), dtype="float32")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vectors / norms).tolist()


def literal(vector: list[float]) -> str:
    """Texto que pgvector entiende como `vector` («[0.1,0.2,…]»)."""
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
