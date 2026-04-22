from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4


logger = logging.getLogger("agenthub.gateway")


def new_request_id() -> str:
    return uuid4().hex[:12]


def start_timer() -> float:
    return perf_counter()


def elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def log_gateway_event(event: str, /, **fields: object) -> None:
    ordered = " ".join(f"{key}={value!r}" for key, value in sorted(fields.items()))
    logger.info("%s %s", event, ordered)
