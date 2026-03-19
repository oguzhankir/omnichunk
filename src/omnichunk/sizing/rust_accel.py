from __future__ import annotations

import importlib
import os
from functools import lru_cache
from typing import Any, Literal, TypedDict

import numpy as np

NwsBackend = Literal["auto", "python", "rust"]

NWS_BACKEND_ENV_VAR = "OMNICHUNK_NWS_BACKEND"

_VALID_BACKENDS: dict[str, NwsBackend] = {
    "auto": "auto",
    "python": "python",
    "rust": "rust",
}


class NwsBackendStatus(TypedDict):
    selected: NwsBackend
    available: bool
    active: bool
    reason: str


def resolve_nws_backend(backend: str | None = None) -> NwsBackend:
    raw = backend if backend is not None else os.getenv(NWS_BACKEND_ENV_VAR, "auto")
    normalized = raw.strip().lower()
    resolved = _VALID_BACKENDS.get(normalized)
    if resolved is None:
        expected = ", ".join(sorted(_VALID_BACKENDS))
        raise ValueError(
            f"Invalid NWS backend '{raw}'. Expected one of: {expected}. "
            f"Use the {NWS_BACKEND_ENV_VAR} environment variable or per-call override."
        )
    return resolved


@lru_cache(maxsize=1)
def _load_rust_module() -> tuple[Any | None, str]:
    try:
        module = importlib.import_module("omnichunk_rust")
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

    fn = getattr(module, "preprocess_nws_cumsum_bytes", None)
    if not callable(fn):
        return None, "omnichunk_rust.preprocess_nws_cumsum_bytes is unavailable"

    return module, ""


def reset_rust_backend_cache() -> None:
    _load_rust_module.cache_clear()


def nws_backend_status(backend: str | None = None) -> NwsBackendStatus:
    selected = resolve_nws_backend(backend)
    module, reason = _load_rust_module()
    available = module is not None
    active = selected == "rust" or (selected == "auto" and available)
    if selected == "python":
        active = False

    return {
        "selected": selected,
        "available": available,
        "active": active,
        "reason": "" if available else reason,
    }


def maybe_preprocess_nws_cumsum_rust(
    code: str,
    *,
    backend: str | None = None,
) -> np.ndarray | None:
    selected = resolve_nws_backend(backend)
    if selected == "python":
        return None

    module, reason = _load_rust_module()
    if module is None:
        if selected == "rust":
            raise RuntimeError(
                "Rust NWS backend was explicitly requested but is unavailable: "
                f"{reason}. Build and install rust/omnichunk_rust first."
            )
        return None

    raw = code.encode("utf-8")
    values = module.preprocess_nws_cumsum_bytes(raw)
    return np.asarray(values, dtype=np.int64)
