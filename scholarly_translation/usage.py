"""Append-only usage event logging.

Never logs source text or credentials. Mock usage is explicitly
labeled synthetic/non-billed rather than pretending cost is zero
because it was "unmeasured".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class UsageEvent:
    run_id: str
    task_id: str
    document_id: str
    provider: str
    model: str
    reason: str
    duration_seconds: float
    outcome: str
    cost_basis: str  # e.g. "synthetic_non_billed" or "unknown"
    token_usage: str = "not_metered"  # mock adapter performs no real inference
    actual_charge: str = "not_metered"  # real spend is unknown, never assumed zero
    estimated_cost_usd: float = 0.0  # known synthetic estimate for mock-only runs
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            object.__setattr__(
                self, "timestamp", datetime.now(timezone.utc).isoformat()
            )

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "document_id": self.document_id,
            "provider": self.provider,
            "model": self.model,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "outcome": self.outcome,
            "cost_basis": self.cost_basis,
            "token_usage": self.token_usage,
            "actual_charge": self.actual_charge,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


def append_usage(event: UsageEvent, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
