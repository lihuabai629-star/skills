#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from session_memory import DEFAULT_CODEX_ROOT, slugify

DEFAULT_SKILLS_ROOT = Path("/root/.codex/skills")


@dataclass(frozen=True)
class MemoryStore:
    scope: str
    path: Path
    domain: str = ""
    project_root: str = ""
    project_slug: str = ""

    @property
    def label(self) -> str:
        if self.scope == "project" and self.project_slug:
            return f"project:{self.project_slug}"
        if self.scope == "domain" and self.domain:
            return f"domain:{self.domain}"
        return self.scope


def normalize_project_root(cwd: str | Path | None) -> str:
    if cwd is None:
        return ""
    text = str(cwd).strip()
    if not text or text == "/":
        return ""
    candidate = Path(text).expanduser()
    candidate = candidate.resolve(strict=False)

    git_root = detect_git_root(candidate)
    if git_root is not None:
        return str(git_root)
    return str(candidate)


def detect_git_root(path: Path) -> Path | None:
    git_cwd = path if path.is_dir() else path.parent
    try:
        output = subprocess.check_output(
            ["git", "-C", str(git_cwd), "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None

    if not output:
        return None
    return Path(output).resolve(strict=False)


def project_slug_for_cwd(cwd: str | Path | None) -> str:
    project_root = normalize_project_root(cwd)
    if not project_root:
        return ""
    return slugify(project_root.strip("/"), fallback="project")


def scope_store(
    *,
    scope: str,
    domain: str = "",
    cwd: str | Path | None = None,
    codex_root: str | Path = DEFAULT_CODEX_ROOT,
    skills_root: str | Path = DEFAULT_SKILLS_ROOT,
) -> MemoryStore:
    codex_root = Path(codex_root)
    skills_root = Path(skills_root)

    if scope == "global":
        return MemoryStore(scope="global", path=codex_root / "memories" / "global" / "lessons", domain=domain)

    if scope == "project":
        project_root = normalize_project_root(cwd)
        if not project_root:
            raise ValueError("project scope requires a meaningful cwd")
        project_slug = project_slug_for_cwd(project_root)
        return MemoryStore(
            scope="project",
            path=codex_root / "memories" / "projects" / project_slug / "lessons",
            domain=domain,
            project_root=project_root,
            project_slug=project_slug,
        )

    if scope == "domain":
        if not domain:
            raise ValueError("domain scope requires a domain name")
        return MemoryStore(
            scope="domain",
            path=skills_root / domain / "references" / "lessons",
            domain=domain,
        )

    raise ValueError(f"unsupported scope: {scope}")


def recall_stores(
    *,
    domain: str = "",
    cwd: str | Path | None = None,
    scope: str = "auto",
    codex_root: str | Path = DEFAULT_CODEX_ROOT,
    skills_root: str | Path = DEFAULT_SKILLS_ROOT,
) -> list[MemoryStore]:
    stores: list[MemoryStore] = []

    if scope in {"auto", "all", "global"}:
        stores.append(scope_store(scope="global", domain=domain, codex_root=codex_root, skills_root=skills_root))

    if scope in {"auto", "all", "project"}:
        project_root = normalize_project_root(cwd)
        if project_root:
            stores.append(
                scope_store(
                    scope="project",
                    domain=domain,
                    cwd=project_root,
                    codex_root=codex_root,
                    skills_root=skills_root,
                )
            )

    if domain and scope in {"auto", "all", "domain"}:
        stores.append(scope_store(scope="domain", domain=domain, codex_root=codex_root, skills_root=skills_root))

    if scope in {"project", "domain"} and not stores:
        raise ValueError(f"no store available for scope={scope}")

    return stores
