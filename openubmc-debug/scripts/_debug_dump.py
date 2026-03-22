#!/usr/bin/env python3
"""Helpers for writing ordered debug dump artifacts."""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
REDACTION = "***"
KEY_VALUE_RE = re.compile(
    r'(?i)(\b(?:access_token|refresh_token|api_token|token|sessionid|session_id|password|secret|csrftoken)\b\s*[:=]\s*"?)([^"\s,;]+)'
)
HEADER_REDACTIONS = [
    re.compile(r"(?im)^((?:authorization)\s*:\s*bearer\s+)(.+)$"),
    re.compile(r"(?im)^((?:cookie|set-cookie)\s*:\s*)(.+)$"),
]
ENV_SECRET_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASS|COOKIE|SESSION(?:ID)?|API_KEY)[A-Z0-9_]*)=([^\s'\";]+)"
)
PRIVATE_KEY_RE = re.compile(
    r"(?is)(-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----)(.*?)(-----END [A-Z0-9 ]*PRIVATE KEY-----)"
)


def _slug(value: str) -> str:
    cooked = SAFE_RE.sub("_", value.strip()).strip("._-")
    return cooked or "artifact"


class DebugDumper:
    def __init__(self, output_dir: str, secrets: Iterable[str] | None = None) -> None:
        self.root = Path(output_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self._counter = 0
        self._artifacts: list[dict[str, object]] = []
        self._lock = threading.Lock()
        self._text_secrets = self._normalize_secrets(secrets)
        self._summary_path = self.root / "summary.json"
        self._created_at = self._timestamp()

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _normalize_secrets(self, secrets: Iterable[str] | None) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for secret in secrets or []:
            if secret is None:
                continue
            cooked = str(secret).strip()
            if not cooked or cooked == REDACTION or cooked in seen:
                continue
            seen.add(cooked)
            unique.append(cooked)
        unique.sort(key=len, reverse=True)
        return unique

    def _next_path(self, label: str, name: str, suffix: str) -> Path:
        path = self.root / f"{self._counter:03d}_{_slug(label)}_{_slug(name)}{suffix}"
        self._counter += 1
        return path

    def _redact_text(self, content: str) -> tuple[str, bool]:
        cooked = content
        redacted = False
        for secret in self._text_secrets:
            if secret in cooked:
                cooked = cooked.replace(secret, REDACTION)
                redacted = True
        for pattern in HEADER_REDACTIONS:
            cooked, count = pattern.subn(r"\1***", cooked)
            redacted = redacted or count > 0
        cooked, count = KEY_VALUE_RE.subn(r"\1***", cooked)
        redacted = redacted or count > 0
        cooked, count = ENV_SECRET_RE.subn(r"\1=***", cooked)
        redacted = redacted or count > 0
        cooked, count = PRIVATE_KEY_RE.subn(r"\1\n***\n\3", cooked)
        redacted = redacted or count > 0
        return cooked, redacted

    def _redact_bytes(self, content: bytes) -> tuple[bytes, bool]:
        cooked, redacted = self._redact_text(content.decode("latin-1"))
        return cooked.encode("latin-1"), redacted

    def _write_summary(self) -> None:
        summary = {
            "created_at": self._created_at,
            "updated_at": self._timestamp(),
            "artifact_count": len(self._artifacts),
            "redacted_artifact_count": sum(1 for item in self._artifacts if item["redacted"]),
            "artifacts": self._artifacts,
        }
        self._summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    def _record(
        self,
        path: Path,
        label: str,
        name: str,
        kind: str,
        redacted: bool,
        metadata: dict[str, object] | None = None,
    ) -> None:
        artifact = {
            "index": len(self._artifacts),
            "filename": path.name,
            "label": label,
            "name": name,
            "kind": kind,
            "size_bytes": path.stat().st_size,
            "redacted": redacted,
            "timestamp": self._timestamp(),
        }
        if metadata:
            artifact["metadata"] = metadata
        self._artifacts.append(artifact)
        self._write_summary()

    def write_text(self, label: str, name: str, content: str, metadata: dict[str, object] | None = None) -> Path:
        cooked, redacted = self._redact_text(content)
        with self._lock:
            path = self._next_path(label, name, ".txt")
            path.write_text(cooked, encoding="utf-8")
            self._record(path, label, name, "text", redacted, metadata=metadata)
        return path

    def write_bytes(self, label: str, name: str, content: bytes, metadata: dict[str, object] | None = None) -> Path:
        cooked, redacted = self._redact_bytes(content)
        with self._lock:
            path = self._next_path(label, name, ".bin")
            path.write_bytes(cooked)
            self._record(path, label, name, "bytes", redacted, metadata=metadata)
        return path


def build_debug_dumper(output_dir: str, secrets: Iterable[str] | None = None):
    return DebugDumper(output_dir, secrets=secrets) if output_dir else None
