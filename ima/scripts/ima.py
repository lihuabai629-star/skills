#!/usr/bin/env python3
"""
Compatibility entrypoint for the IMA web skill.
Delegates to `run.py ask_knowledge.py`.
"""

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RUNNER_PATH = SCRIPT_DIR / "run.py"
KNOWLEDGE_PREFIXES = ("@knowledge", "@个人知识库")


def parse_query_request(raw_query: str) -> dict[str, object]:
    query = raw_query.strip()
    for prefix in KNOWLEDGE_PREFIXES:
        if query.startswith(prefix):
            return {
                "question": query[len(prefix) :].strip(),
                "knowledge_mode": True,
            }
    return {
        "question": query,
        "knowledge_mode": False,
    }


def build_run_command(request: dict[str, object], show_browser: bool = False) -> list[str]:
    command = [
        sys.executable,
        str(RUNNER_PATH),
        "ask_knowledge.py",
        "--question",
        str(request["question"]),
        "--scope",
        "knowledge" if request["knowledge_mode"] else "public",
    ]
    if show_browser:
        command.append("--show-browser")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask questions through the IMA web skill")
    parser.add_argument("query", nargs="?", help="Question to ask")
    parser.add_argument("--autoclose", default="false", help="Ignored for web mode compatibility")
    parser.add_argument("--show-browser", action="store_true", help="Show browser while asking")
    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        return 0

    request = parse_query_request(args.query)
    command = build_run_command(request, show_browser=args.show_browser)
    result = subprocess.run(command)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
