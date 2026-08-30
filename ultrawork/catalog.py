"""Validated, read-only public-profile catalog snapshots."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True, slots=True)
class Catalog:
    board: str
    profiles: tuple[dict, ...]
    revision: str

    @classmethod
    def from_profiles(cls, profiles: list[dict] | tuple[dict, ...], board: str) -> "Catalog":
        if not isinstance(board, str) or not board or not isinstance(profiles, (list, tuple)):
            raise ValueError("catalog must contain a board and profile list")
        cleaned = []
        for profile in profiles:
            if not isinstance(profile, dict) or set(profile) - {"name", "on_disk", "running_count", "ready_count", "todo_count"}:
                raise ValueError("invalid catalog profile")
            name = profile.get("name")
            if not isinstance(name, str) or not name or not isinstance(profile.get("on_disk"), bool):
                raise ValueError("invalid catalog profile")
            counts = {key: profile.get(key, 0) for key in ("running_count", "ready_count", "todo_count")}
            if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts.values()):
                raise ValueError("invalid catalog counts")
            cleaned.append({"name": name, "on_disk": profile["on_disk"], **counts})
        if len({profile["name"] for profile in cleaned}) != len(cleaned):
            raise ValueError("duplicate catalog profile")
        ordered = tuple(sorted(cleaned, key=lambda item: item["name"].encode("ascii", "strict")))
        canonical = json.dumps({"board": board, "profiles": ordered}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return cls(board, ordered, hashlib.sha256(canonical.encode()).hexdigest())
