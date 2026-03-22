#!/usr/bin/env python3
"""Shared CLI helpers for openUBMC remote scripts."""
from __future__ import annotations

import os


def resolve_value(default_value: str, env_name: str, label: str) -> str:
    if env_name:
        if env_name not in os.environ:
            raise SystemExit(f"{label} environment variable {env_name} is not set")
        return os.environ[env_name]
    return default_value


def resolve_ssh_credentials(args) -> dict[str, str | int]:
    return {
        "user": resolve_value(args.ssh_user, args.ssh_user_env, "SSH user"),
        "password": resolve_value(args.ssh_password, args.ssh_password_env, "SSH password"),
        "port": args.ssh_port,
        "identity_file": args.ssh_identity_file,
    }


def resolve_telnet_credentials(args) -> dict[str, str | int]:
    return {
        "user": resolve_value(args.telnet_user, args.telnet_user_env, "Telnet user"),
        "password": resolve_value(args.telnet_password, args.telnet_password_env, "Telnet password"),
        "port": args.telnet_port,
    }
