#!/usr/bin/env python3
"""Regression coverage for openubmc-debug helper scripts."""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import json
import argparse
import importlib.util
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TEST_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = TEST_DIR / "fixtures"
SCRIPT_DIR = TEST_DIR.parent / "scripts"
SKILL_ROOT = TEST_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import _telnet_common  # noqa: E402
import _remote_common as remote_common  # noqa: E402
import busctl_remote  # noqa: E402
import collect_logs  # noqa: E402
import mdbctl_remote  # noqa: E402
import preflight_remote  # noqa: E402
from _remote_common import build_filter_notice, preview_lines, sanitize_remote_text  # noqa: E402


def read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def read_skill_file(path: str) -> str:
    return (SKILL_ROOT / path).read_text(encoding="utf-8")


def parse_with_argv(parse_fn, argv: list[str]):
    with mock.patch.object(sys, "argv", argv):
        return parse_fn()


def assert_common_json_contract(testcase: unittest.TestCase, payload: dict[str, object], tool: str) -> None:
    testcase.assertEqual(payload["schema_version"], "openubmc-debug.v1")
    testcase.assertEqual(payload["tool"], tool)
    testcase.assertIsInstance(payload["request"], dict)
    testcase.assertIsInstance(payload["result"], dict)
    testcase.assertIsInstance(payload["warnings"], list)


def load_script_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SKILL_ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTelnet:
    def __init__(self) -> None:
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def close(self) -> None:
        return None


class FakeTelnetCommand:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def read_until(self, _expected: bytes, timeout: float = 0) -> bytes:
        if self.chunks:
            return self.chunks.pop(0)
        return b""


class RemoteCommonTests(unittest.TestCase):
    def test_sanitize_remote_text_strips_noise_and_preserves_indentation(self) -> None:
        raw = read_fixture("ssh_banner_busctl_tree.txt")

        self.assertEqual(
            sanitize_remote_text(raw),
            (
                "  /bmc/kepler/Chassis/1/SensorSelInfo\n"
                "DBUS_SESSION_BUS_ADDRESS=unix:abstract=/tmp/dbus-test,guid=1234"
            ),
        )

    def test_busctl_filter_stdout_returns_notice_when_filters_remove_everything(self) -> None:
        stdout = read_fixture("busctl_tree.txt")

        self.assertEqual(
            busctl_remote.filter_stdout(stdout, "missing", 1, None),
            "[INFO] 0 matching lines after filters (grep=missing; head=1)",
        )
        self.assertEqual(
            busctl_remote.filter_stdout(stdout, "sensorselinfo", 1, None),
            "/bmc/kepler/Chassis/1/SensorSelInfo",
        )
        self.assertEqual(
            build_filter_notice(["SensorSelInfo"], None, 2),
            "[INFO] 0 matching lines after filters (grep=SensorSelInfo; tail=2)",
        )

    def test_preview_lines_truncates_without_losing_order(self) -> None:
        text = "first line\n" + ("x" * 40) + "\nthird line"

        self.assertEqual(preview_lines(text, limit=2, width=12), ["first line", "xxxxxxxxx..."])

    def test_detect_dbus_env_uses_posix_login_shell_wrapper(self) -> None:
        with mock.patch.object(
            remote_common,
            "run_ssh",
            return_value=subprocess.CompletedProcess(
                args=["ssh"],
                returncode=0,
                stdout=(
                    "DBUS_SESSION_BUS_ADDRESS=unix:abstract=/tmp/dbus-test,guid=1234\n"
                    "XDG_RUNTIME_DIR=/run/user/502\n"
                ),
                stderr="",
            ),
        ) as run_ssh:
            env = remote_common.detect_dbus_env(
                "10.121.177.97",
                "Administrator",
                "Admin@9000",
                5,
            )

        self.assertEqual(env["XDG_RUNTIME_DIR"], "/run/user/502")
        remote_cmd = run_ssh.call_args.args[3]
        self.assertTrue(remote_cmd.startswith("sh -lc "))
        self.assertNotIn("bash -ilc", remote_cmd)


class MdbctlRemoteTests(unittest.TestCase):
    def test_build_login_shell_cmd_uses_posix_profile_loading(self) -> None:
        cmd = mdbctl_remote.build_login_shell_cmd(["lsclass"])

        self.assertTrue(cmd.startswith("sh -lc "))
        self.assertIn(". /etc/profile >/dev/null 2>&1;", cmd)
        self.assertNotIn("source /etc/profile", cmd)
        self.assertNotIn("bash -ilc", cmd)

    def test_classify_failure_recognizes_known_error_shapes(self) -> None:
        service_unknown = read_fixture("mdbctl_service_unknown.txt")
        ssh_timeout = read_fixture("ssh_timeout.txt")
        ssh_auth_failed = read_fixture("ssh_auth_failed.txt")

        self.assertEqual(
            mdbctl_remote.classify_failure(
                subprocess.CompletedProcess(args=["ssh"], returncode=1, stdout="", stderr=service_unknown),
                "",
                service_unknown,
            ),
            "service-unknown",
        )
        self.assertEqual(
            mdbctl_remote.classify_failure(
                subprocess.CompletedProcess(args=["ssh"], returncode=127, stdout="", stderr="bash: mdbctl: command not found"),
                "",
                "bash: mdbctl: command not found",
            ),
            "command-not-found",
        )
        self.assertEqual(
            mdbctl_remote.classify_failure(
                subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="", stderr=""),
                "",
                "",
            ),
            "empty-output",
        )
        self.assertEqual(
            mdbctl_remote.classify_failure(
                subprocess.CompletedProcess(args=["ssh"], returncode=124, stdout="", stderr=ssh_timeout),
                "",
                ssh_timeout,
            ),
            "timeout",
        )
        self.assertEqual(
            mdbctl_remote.classify_failure(
                subprocess.CompletedProcess(args=["ssh"], returncode=255, stdout="", stderr=ssh_auth_failed),
                "",
                ssh_auth_failed,
            ),
            "remote-command-failed",
        )


class CollectLogsTests(unittest.TestCase):
    def test_filter_lines_and_empty_message_include_filter_context(self) -> None:
        lines = [
            "2026-03-17 09:00:00 sensor INFO: boot message",
            "2026-03-17 10:00:00 thermal INFO: fan update",
            "2026-03-17 10:30:00 sensor ERROR: scan failed",
        ]

        self.assertEqual(
            collect_logs.filter_lines(lines, "2026-03-17 10:00:00", ["sensor"]),
            ["2026-03-17 10:30:00 sensor ERROR: scan failed"],
        )
        self.assertEqual(
            collect_logs.build_empty_message("/var/log/app.log", "2026-03-17 10:00:00", ["sensor"]),
            "[INFO] 0 matching lines for /var/log/app.log after filters (grep=sensor; since_boot>=2026-03-17 10:00:00)",
        )


class FakeSocket:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.sent: list[bytes] = []
        self.timeout = None
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def recv(self, _size: int) -> bytes:
        if self.chunks:
            return self.chunks.pop(0)
        return b""

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True


class TelnetCommonTests(unittest.TestCase):
    def test_module_no_longer_imports_telnetlib(self) -> None:
        source = read_skill_file("scripts/_telnet_common.py")
        self.assertNotIn("telnetlib", source)

    def test_minimal_telnet_client_handles_negotiation_and_expect(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "_minimal_telnet",
            SKILL_ROOT / "scripts" / "_minimal_telnet.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        fake_socket = FakeSocket([b"\xff\xfb\x01login: "])
        with mock.patch.object(module.socket, "create_connection", return_value=fake_socket):
            client = module.TelnetClient("10.121.177.97", 23, timeout=2)
            index, match, data = client.expect([_telnet_common.LOGIN_RE], timeout=1)

        self.assertEqual(index, 0)
        self.assertIsNotNone(match)
        self.assertEqual(data, b"login:")
        self.assertTrue(fake_socket.sent)
        self.assertEqual(fake_socket.sent[0], b"\xff\xfe\x01")

    def test_telnet_connect_handles_login_prompt(self) -> None:
        fake_telnet = FakeTelnet()
        responses = [
            (0, b"login: "),
            (0, b"Password: "),
            (0, b"~ # "),
        ]

        def fake_expect(_tn, _patterns, timeout=None, debug_dumper=None, debug_name="telnet_expect"):
            return responses.pop(0)

        with mock.patch.object(_telnet_common, "TelnetClient", return_value=fake_telnet):
            with mock.patch.object(_telnet_common, "_expect", side_effect=fake_expect):
                tn = _telnet_common.telnet_connect(
                    "10.121.177.97",
                    23,
                    "Administrator",
                    "Admin@9000",
                    connect_timeout=2,
                    prompt_timeout=2,
                )

        self.assertIs(tn, fake_telnet)
        self.assertEqual(fake_telnet.writes, [b"Administrator\n", b"Admin@9000\n"])


class DebugDumpTests(unittest.TestCase):
    def test_scripts_accept_debug_dump_argument(self) -> None:
        busctl_args = parse_with_argv(
            busctl_remote.parse_args,
            ["busctl_remote.py", "--ip", "10.121.177.97", "--debug-dump", "/tmp/openubmc-dump"],
        )
        mdbctl_args = parse_with_argv(
            mdbctl_remote.parse_args,
            ["mdbctl_remote.py", "--ip", "10.121.177.97", "--debug-dump", "/tmp/openubmc-dump"],
        )
        collect_args = parse_with_argv(
            collect_logs.parse_args,
            ["collect_logs.py", "--ip", "10.121.177.97", "--debug-dump", "/tmp/openubmc-dump"],
        )
        preflight_args = parse_with_argv(
            preflight_remote.parse_args,
            ["preflight_remote.py", "--ip", "10.121.177.97", "--debug-dump", "/tmp/openubmc-dump"],
        )

        self.assertEqual(busctl_args.debug_dump, "/tmp/openubmc-dump")
        self.assertEqual(mdbctl_args.debug_dump, "/tmp/openubmc-dump")
        self.assertEqual(collect_args.debug_dump, "/tmp/openubmc-dump")
        self.assertEqual(preflight_args.debug_dump, "/tmp/openubmc-dump")

    def test_debug_dumper_writes_ordered_files_redacts_secrets_and_emits_summary(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "_debug_dump",
            SKILL_ROOT / "scripts" / "_debug_dump.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            dumper = module.build_debug_dumper(tmpdir, secrets=["Admin@9000"])
            dumper.write_text("ssh", "command", "sshpass -p 'Admin@9000' ssh Administrator@10.0.0.1 date")
            dumper.write_bytes("telnet", "raw", b"\x1epassword: Admin@9000\x1f")

            files = sorted(Path(tmpdir).iterdir())
            self.assertEqual(len(files), 3)
            self.assertTrue(files[0].name.endswith("_ssh_command.txt"))
            self.assertTrue(files[1].name.endswith("_telnet_raw.bin"))
            self.assertEqual(files[2].name, "summary.json")
            self.assertNotIn("Admin@9000", files[0].read_text(encoding="utf-8"))
            self.assertIn("***", files[0].read_text(encoding="utf-8"))
            self.assertNotIn(b"Admin@9000", files[1].read_bytes())
            self.assertIn(b"***", files[1].read_bytes())
            summary = json.loads(files[2].read_text(encoding="utf-8"))
            self.assertIn("created_at", summary)
            self.assertEqual(len(summary["artifacts"]), 2)
            self.assertEqual(summary["artifacts"][0]["filename"], files[0].name)
            self.assertTrue(summary["artifacts"][0]["redacted"])
            self.assertIn("timestamp", summary["artifacts"][0])
            self.assertEqual(summary["artifacts"][1]["filename"], files[1].name)

    def test_debug_dumper_redacts_token_cookie_and_private_key_shapes(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "_debug_dump",
            SKILL_ROOT / "scripts" / "_debug_dump.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            dumper = module.build_debug_dumper(tmpdir, secrets=[])
            dumper.write_text(
                "http",
                "headers",
                (
                    "Authorization: Bearer abc123\n"
                    "Cookie: sid=xyz; csrftoken=qwe\n"
                    "access_token=toktok\n"
                    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
                    "verysecret\n"
                    "-----END OPENSSH PRIVATE KEY-----\n"
                ),
            )
            dumper.write_bytes("telnet", "raw", b"sessionid=abc123\napi_token=qwe")

            dump_dir = Path(tmpdir)
            text_dump = next(path for path in dump_dir.iterdir() if path.name.endswith("_http_headers.txt"))
            byte_dump = next(path for path in dump_dir.iterdir() if path.name.endswith("_telnet_raw.bin"))
            self.assertNotIn("abc123", text_dump.read_text(encoding="utf-8"))
            self.assertNotIn("xyz", text_dump.read_text(encoding="utf-8"))
            self.assertNotIn("qwe", text_dump.read_text(encoding="utf-8"))
            self.assertNotIn("verysecret", text_dump.read_text(encoding="utf-8"))
            self.assertIn("***", text_dump.read_text(encoding="utf-8"))
            self.assertNotIn(b"abc123", byte_dump.read_bytes())
            self.assertNotIn(b"qwe", byte_dump.read_bytes())
            self.assertIn(b"***", byte_dump.read_bytes())

    def test_run_ssh_and_telnet_command_can_emit_redacted_debug_artifacts(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "_debug_dump",
            SKILL_ROOT / "scripts" / "_debug_dump.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            dumper = module.build_debug_dumper(tmpdir, secrets=["Admin@9000"])
            with mock.patch.object(
                remote_common.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="ssh-out Admin@9000", stderr="ssh-err"),
            ):
                remote_common.run_ssh(
                    "10.121.177.97",
                    "Administrator",
                    "Admin@9000",
                    "date",
                    5,
                    debug_dumper=dumper,
                    debug_label="preflight_ssh",
                )

            telnet = FakeTelnetCommand([b"\x1eraw Admin@9000 telnet\x1f"])
            _telnet_common.run_cmd(
                telnet,
                "date",
                timeout=1,
                debug_dumper=dumper,
                debug_name="preflight_telnet",
            )

            names = sorted(path.name for path in Path(tmpdir).iterdir())
            self.assertTrue(any(name.endswith("_preflight_ssh_command.txt") for name in names))
            self.assertTrue(any(name.endswith("_preflight_ssh_stdout.txt") for name in names))
            self.assertTrue(any(name.endswith("_preflight_telnet_raw.bin") for name in names))
            self.assertTrue(any(name.endswith("_preflight_telnet_text.txt") for name in names))
            self.assertIn("summary.json", names)

            dump_dir = Path(tmpdir)
            ssh_command = next(path for path in dump_dir.iterdir() if path.name.endswith("_preflight_ssh_command.txt"))
            ssh_stdout = next(path for path in dump_dir.iterdir() if path.name.endswith("_preflight_ssh_stdout.txt"))
            telnet_raw = next(path for path in dump_dir.iterdir() if path.name.endswith("_preflight_telnet_raw.bin"))
            telnet_text = next(path for path in dump_dir.iterdir() if path.name.endswith("_preflight_telnet_text.txt"))
            self.assertNotIn("Admin@9000", ssh_command.read_text(encoding="utf-8"))
            self.assertNotIn("Admin@9000", ssh_stdout.read_text(encoding="utf-8"))
            self.assertNotIn(b"Admin@9000", telnet_raw.read_bytes())
            self.assertNotIn("Admin@9000", telnet_text.read_text(encoding="utf-8"))
            summary = json.loads((Path(tmpdir) / "summary.json").read_text(encoding="utf-8"))
            self.assertIn("metadata", summary["artifacts"][0])
            self.assertIn("stage", summary["artifacts"][0]["metadata"])


class BusctlJsonTests(unittest.TestCase):
    def test_busctl_parse_args_accepts_json_flag(self) -> None:
        args = parse_with_argv(
            busctl_remote.parse_args,
            ["busctl_remote.py", "--ip", "10.121.177.97", "--json"],
        )
        self.assertTrue(args.json)

    def test_busctl_main_can_emit_machine_readable_json(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "busctl_remote.py",
                    "--ip",
                    "10.121.177.97",
                    "--action",
                    "tree",
                    "--service",
                    "bmc.kepler.sensor",
                    "--grep",
                    "SensorSelInfo",
                    "--head",
                    "1",
                    "--json",
                ],
            ),
            mock.patch.object(
                busctl_remote,
                "resolve_ssh_credentials",
                return_value={"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""},
            ),
            mock.patch.object(busctl_remote, "build_debug_dumper", return_value=None),
            mock.patch.object(
                busctl_remote,
                "detect_dbus_env",
                return_value={
                    "DBUS_SESSION_BUS_ADDRESS": "unix:abstract=/tmp/dbus-test,guid=1234",
                    "XDG_RUNTIME_DIR": "/run/user/502",
                },
            ),
            mock.patch.object(
                busctl_remote,
                "run_ssh",
                return_value=subprocess.CompletedProcess(
                    args=["ssh"],
                    returncode=0,
                    stdout=read_fixture("busctl_tree.txt"),
                    stderr="",
                ),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            rc = busctl_remote.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "busctl_remote")
        self.assertEqual(rc, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["code"], "ok")
        self.assertEqual(payload["request"]["action"], "tree")
        self.assertIn("dbus_env", payload["result"])
        self.assertEqual(payload["action"], "tree")
        self.assertEqual(payload["service"], "bmc.kepler.sensor")
        self.assertEqual(payload["returncode"], 0)
        self.assertEqual(payload["stdout"], "/bmc/kepler/Chassis/1/SensorSelInfo")
        self.assertEqual(payload["stdout_lines"], ["/bmc/kepler/Chassis/1/SensorSelInfo"])
        self.assertEqual(payload["stderr"], "")
        self.assertEqual(payload["stderr_lines"], [])
        self.assertEqual(
            payload["dbus_env"],
            {
                "DBUS_SESSION_BUS_ADDRESS": "unix:abstract=/tmp/dbus-test,guid=1234",
                "XDG_RUNTIME_DIR": "/run/user/502",
            },
        )

    def test_busctl_json_reports_missing_dbus_env(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["busctl_remote.py", "--ip", "10.121.177.97", "--json"]),
            mock.patch.object(
                busctl_remote,
                "resolve_ssh_credentials",
                return_value={"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""},
            ),
            mock.patch.object(busctl_remote, "build_debug_dumper", return_value=None),
            mock.patch.object(busctl_remote, "detect_dbus_env", return_value={}),
            mock.patch.object(busctl_remote, "run_ssh") as run_ssh,
            contextlib.redirect_stdout(stdout),
        ):
            rc = busctl_remote.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "busctl_remote")
        self.assertEqual(rc, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "dbus_env_missing")
        self.assertEqual(payload["returncode"], 2)
        self.assertEqual(payload["stdout"], "")
        self.assertIn("Failed to detect DBUS/XDG env", payload["stderr"])
        self.assertFalse(run_ssh.called)


class MdbctlJsonTests(unittest.TestCase):
    def test_mdbctl_parse_args_accepts_json_flag(self) -> None:
        args = parse_with_argv(
            mdbctl_remote.parse_args,
            ["mdbctl_remote.py", "--ip", "10.121.177.97", "--json"],
        )
        self.assertTrue(args.json)

    def test_mdbctl_main_can_emit_machine_readable_json(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(
                sys,
                "argv",
                ["mdbctl_remote.py", "--ip", "10.121.177.97", "--json", "lsclass"],
            ),
            mock.patch.object(
                mdbctl_remote,
                "resolve_ssh_credentials",
                return_value={"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""},
            ),
            mock.patch.object(mdbctl_remote, "build_debug_dumper", return_value=None),
            mock.patch.object(
                mdbctl_remote,
                "run_ssh",
                return_value=subprocess.CompletedProcess(
                    args=["ssh"],
                    returncode=0,
                    stdout="DiscreteSensor\nThresholdSensor\n",
                    stderr="",
                ),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            rc = mdbctl_remote.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "mdbctl_remote")
        self.assertEqual(rc, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["code"], "ok")
        self.assertEqual(payload["request"]["command_parts"], ["lsclass"])
        self.assertEqual(payload["result"]["selected_mode"], "login-shell")
        self.assertEqual(payload["requested_mode"], "auto")
        self.assertEqual(payload["selected_mode"], "login-shell")
        self.assertEqual(payload["command_parts"], ["lsclass"])
        self.assertEqual(payload["stdout_lines"], ["DiscreteSensor", "ThresholdSensor"])
        self.assertEqual(payload["attempts"], [{"mode": "login-shell", "classification": "ok", "returncode": 0}])

    def test_mdbctl_json_reports_final_failure_classification(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(
                sys,
                "argv",
                ["mdbctl_remote.py", "--ip", "10.121.177.97", "--mode", "direct-skynet", "--json", "lsclass"],
            ),
            mock.patch.object(
                mdbctl_remote,
                "resolve_ssh_credentials",
                return_value={"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""},
            ),
            mock.patch.object(mdbctl_remote, "build_debug_dumper", return_value=None),
            mock.patch.object(
                mdbctl_remote,
                "run_ssh",
                return_value=subprocess.CompletedProcess(
                    args=["ssh"],
                    returncode=1,
                    stdout="",
                    stderr=read_fixture("mdbctl_service_unknown.txt"),
                ),
            ),
            contextlib.redirect_stdout(stdout),
        ):
            rc = mdbctl_remote.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "mdbctl_remote")
        self.assertEqual(rc, mdbctl_remote.CLASS_EXIT_CODES["service-unknown"])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "service-unknown")
        self.assertEqual(payload["selected_mode"], None)
        self.assertEqual(payload["returncode"], mdbctl_remote.CLASS_EXIT_CODES["service-unknown"])
        self.assertEqual(payload["attempts"], [{"mode": "direct-skynet", "classification": "service-unknown", "returncode": 1}])
        self.assertIn("busctl_remote.py", payload["hint"])


class CollectLogsJsonTests(unittest.TestCase):
    def test_collect_logs_parse_args_accepts_json_flag(self) -> None:
        args = parse_with_argv(
            collect_logs.parse_args,
            ["collect_logs.py", "--ip", "10.121.177.97", "--json"],
        )
        self.assertTrue(args.json)

    def test_collect_logs_main_can_emit_machine_readable_json(self) -> None:
        stdout = io.StringIO()
        telnet = object()
        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "collect_logs.py",
                    "--ip",
                    "10.121.177.97",
                    "--logs",
                    "app.log",
                    "--grep",
                    "sensor",
                    "--since-boot",
                    "--json",
                ],
            ),
            mock.patch.object(
                collect_logs,
                "resolve_telnet_credentials",
                return_value={"user": "Administrator", "password": "Admin@9000", "port": 23},
            ),
            mock.patch.object(collect_logs, "build_debug_dumper", return_value=None),
            mock.patch.object(collect_logs, "telnet_connect", return_value=telnet),
            mock.patch.object(collect_logs, "get_boot_time_str", return_value="2026-03-17 10:00:00"),
            mock.patch.object(collect_logs, "list_log_files", return_value=["/var/log/app.log"]),
            mock.patch.object(
                collect_logs,
                "run_cmd",
                return_value=(
                    "2026-03-17 09:00:00 sensor INFO: boot message\n"
                    "2026-03-17 10:30:00 sensor ERROR: scan failed\n"
                    "2026-03-17 10:45:00 thermal INFO: fan update\n"
                ),
            ),
            mock.patch.object(collect_logs, "close_telnet"),
            contextlib.redirect_stdout(stdout),
        ):
            rc = collect_logs.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "collect_logs")
        self.assertEqual(rc, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["code"], "ok")
        self.assertEqual(payload["request"]["logs_requested"], ["app.log"])
        self.assertIn("entries", payload["result"])
        self.assertEqual(payload["boot_time"], "2026-03-17 10:00:00")
        self.assertEqual(payload["keywords"], ["sensor"])
        self.assertEqual(payload["entries"][0]["path"], "/var/log/app.log")
        self.assertEqual(payload["entries"][0]["line_count"], 1)
        self.assertEqual(payload["entries"][0]["lines"], ["2026-03-17 10:30:00 sensor ERROR: scan failed"])
        self.assertFalse(payload["entries"][0]["empty"])

    def test_collect_logs_json_reports_telnet_connect_failure(self) -> None:
        stdout = io.StringIO()
        login_stuck = read_fixture("telnet_login_stuck.txt").strip()
        with (
            mock.patch.object(sys, "argv", ["collect_logs.py", "--ip", "10.121.177.97", "--json"]),
            mock.patch.object(
                collect_logs,
                "resolve_telnet_credentials",
                return_value={"user": "Administrator", "password": "Admin@9000", "port": 23},
            ),
            mock.patch.object(collect_logs, "build_debug_dumper", return_value=None),
            mock.patch.object(collect_logs, "telnet_connect", side_effect=RuntimeError(login_stuck)),
            contextlib.redirect_stdout(stdout),
        ):
            rc = collect_logs.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "collect_logs")
        self.assertEqual(rc, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "telnet_connect_failed")
        self.assertEqual(payload["returncode"], 2)
        self.assertIn("login:", payload["error"])

    def test_collect_logs_json_reports_telnet_connect_timeout(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["collect_logs.py", "--ip", "10.121.177.97", "--json"]),
            mock.patch.object(
                collect_logs,
                "resolve_telnet_credentials",
                return_value={"user": "Administrator", "password": "Admin@9000", "port": 23},
            ),
            mock.patch.object(collect_logs, "build_debug_dumper", return_value=None),
            mock.patch.object(collect_logs, "telnet_connect", side_effect=TimeoutError("timed out")),
            contextlib.redirect_stdout(stdout),
        ):
            rc = collect_logs.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "collect_logs")
        self.assertEqual(rc, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "telnet_connect_failed")
        self.assertEqual(payload["returncode"], 2)
        self.assertIn("timed out", payload["error"])


class PreflightJsonTests(unittest.TestCase):
    def _expected_busctl_command(self) -> str:
        script = Path(preflight_remote.__file__).resolve().with_name("busctl_remote.py")
        return (
            f"python {script} --ip 10.121.177.97 --ssh-user Administrator "
            "--ssh-password-env SSH_PASS --action tree --service bmc.kepler.sensor"
        )

    def _expected_print_env_command(self) -> str:
        script = Path(preflight_remote.__file__).resolve().with_name("busctl_remote.py")
        return f"python {script} --ip 10.121.177.97 --ssh-user Administrator --ssh-password-env SSH_PASS --print-env"

    def test_preflight_parse_args_accepts_json_flag(self) -> None:
        args = parse_with_argv(
            preflight_remote.parse_args,
            ["preflight_remote.py", "--ip", "10.121.177.97", "--json"],
        )
        self.assertTrue(args.json)

    def test_preflight_main_can_emit_machine_readable_json(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["preflight_remote.py", "--ip", "10.121.177.97", "--json"]),
            mock.patch.object(preflight_remote, "resolve_ssh_credentials", return_value={"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""}),
            mock.patch.object(preflight_remote, "resolve_telnet_credentials", return_value={"user": "Administrator", "password": "Admin@9000", "port": 23}),
            mock.patch.object(preflight_remote, "build_debug_dumper", return_value=None),
            mock.patch.object(preflight_remote, "check_ssh", return_value=(True, ["2026-03-17 07:37:58 CGP"])),
            mock.patch.object(
                preflight_remote,
                "check_dbus_env",
                return_value=(
                    True,
                    [
                        "DBUS_SESSION_BUS_ADDRESS=unix:abstract=/tmp/dbus-test,guid=1234",
                        "XDG_RUNTIME_DIR=/run/user/502",
                    ],
                    {
                        "DBUS_SESSION_BUS_ADDRESS": "unix:abstract=/tmp/dbus-test,guid=1234",
                        "XDG_RUNTIME_DIR": "/run/user/502",
                    },
                ),
            ),
            mock.patch.object(preflight_remote, "check_mdbctl", return_value=(False, ["service unknown"])),
            mock.patch.object(preflight_remote, "check_busctl", return_value=(True, ["└─/bmc/kepler"])),
            mock.patch.object(preflight_remote, "check_telnet", return_value=(True, ["/var/log/app.log"])),
            contextlib.redirect_stdout(stdout),
        ):
            rc = preflight_remote.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "preflight_remote")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["ip"], "10.121.177.97")
        self.assertFalse(payload["overall_ok"])
        self.assertIn("checks", payload["result"])
        self.assertEqual(payload["overall_code"], "preflight_failed")
        self.assertEqual(payload["failure_count"], 1)
        self.assertEqual(payload["failed_checks"], ["MDBCTL"])
        self.assertEqual(
            payload["recommended_next_step"],
            "Prefer busctl_remote.py for object queries; do not keep retrying mdbctl.",
        )
        self.assertEqual(payload["recommended_command"], self._expected_busctl_command())
        self.assertEqual(payload["checks"]["SSH"]["code"], "ok")
        self.assertEqual(payload["checks"]["SSH"]["status"], "OK")
        self.assertEqual(
            payload["checks"]["SSH"]["recommended_next_step"],
            "Continue with busctl_remote.py for object queries or collect_logs.py for log queries.",
        )
        self.assertEqual(payload["checks"]["SSH"]["recommended_command"], self._expected_busctl_command())
        self.assertEqual(payload["checks"]["DBUS_ENV"]["code"], "ok")
        self.assertEqual(payload["checks"]["MDBCTL"]["code"], "mdbctl_unavailable")
        self.assertEqual(payload["checks"]["MDBCTL"]["status"], "FAIL")
        self.assertEqual(payload["checks"]["MDBCTL"]["lines"], ["service unknown"])
        self.assertEqual(
            payload["checks"]["MDBCTL"]["recommended_next_step"],
            "Prefer busctl_remote.py for object queries; do not keep retrying mdbctl.",
        )
        self.assertEqual(payload["checks"]["MDBCTL"]["recommended_command"], self._expected_busctl_command())
        self.assertEqual(payload["checks"]["DBUS_ENV"]["env"]["XDG_RUNTIME_DIR"], "/run/user/502")

    def test_preflight_json_uses_stable_codes_for_each_failed_check(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["preflight_remote.py", "--ip", "10.121.177.97", "--json"]),
            mock.patch.object(preflight_remote, "resolve_ssh_credentials", return_value={"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""}),
            mock.patch.object(preflight_remote, "resolve_telnet_credentials", return_value={"user": "Administrator", "password": "Admin@9000", "port": 23}),
            mock.patch.object(preflight_remote, "build_debug_dumper", return_value=None),
            mock.patch.object(preflight_remote, "check_ssh", return_value=(False, ["ssh timeout"])),
            mock.patch.object(preflight_remote, "check_dbus_env", return_value=(False, ["missing env"], {})),
            mock.patch.object(preflight_remote, "check_mdbctl", return_value=(False, ["mdbctl failed"])),
            mock.patch.object(preflight_remote, "check_busctl", return_value=(False, ["busctl failed"])),
            mock.patch.object(preflight_remote, "check_telnet", return_value=(False, ["login prompt not reached"])),
            contextlib.redirect_stdout(stdout),
        ):
            rc = preflight_remote.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "preflight_remote")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["overall_code"], "preflight_failed")
        self.assertEqual(payload["failure_count"], 5)
        self.assertEqual(payload["failed_checks"], ["SSH", "DBUS_ENV", "MDBCTL", "BUSCTL", "TELNET"])
        self.assertEqual(
            payload["recommended_next_step"],
            "Fall back to local-only analysis or verify SSH credentials/port before object queries.",
        )
        self.assertEqual(payload["recommended_command"], "ssh -o ConnectTimeout=5 Administrator@10.121.177.97 exit")
        self.assertEqual(payload["checks"]["SSH"]["code"], "ssh_unavailable")
        self.assertEqual(
            payload["checks"]["SSH"]["recommended_next_step"],
            "Fall back to local-only analysis or verify SSH credentials/port before object queries.",
        )
        self.assertEqual(payload["checks"]["SSH"]["recommended_command"], "ssh -o ConnectTimeout=5 Administrator@10.121.177.97 exit")
        self.assertEqual(payload["checks"]["DBUS_ENV"]["code"], "dbus_env_missing")
        self.assertEqual(
            payload["checks"]["DBUS_ENV"]["recommended_next_step"],
            "Run busctl_remote.py --print-env or open an interactive SSH shell to inspect DBUS/XDG.",
        )
        self.assertEqual(payload["checks"]["DBUS_ENV"]["recommended_command"], self._expected_print_env_command())
        self.assertEqual(payload["checks"]["MDBCTL"]["code"], "mdbctl_unavailable")
        self.assertEqual(
            payload["checks"]["MDBCTL"]["recommended_next_step"],
            "Prefer busctl_remote.py for object queries; do not keep retrying mdbctl.",
        )
        self.assertEqual(payload["checks"]["MDBCTL"]["recommended_command"], self._expected_busctl_command())
        self.assertEqual(payload["checks"]["BUSCTL"]["code"], "busctl_unavailable")
        self.assertEqual(
            payload["checks"]["BUSCTL"]["recommended_next_step"],
            "Open an interactive SSH shell and re-check DBUS/XDG before retrying busctl.",
        )
        self.assertEqual(payload["checks"]["BUSCTL"]["recommended_command"], self._expected_print_env_command())
        self.assertEqual(payload["checks"]["TELNET"]["code"], "telnet_unavailable")
        self.assertEqual(
            payload["checks"]["TELNET"]["recommended_next_step"],
            "Request a log bundle or restore Telnet access before log collection.",
        )
        self.assertEqual(payload["checks"]["TELNET"]["recommended_command"], "telnet 10.121.177.97 23")

    def test_preflight_json_reports_ok_overall_code_when_all_checks_pass(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["preflight_remote.py", "--ip", "10.121.177.97", "--json"]),
            mock.patch.object(preflight_remote, "resolve_ssh_credentials", return_value={"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""}),
            mock.patch.object(preflight_remote, "resolve_telnet_credentials", return_value={"user": "Administrator", "password": "Admin@9000", "port": 23}),
            mock.patch.object(preflight_remote, "build_debug_dumper", return_value=None),
            mock.patch.object(preflight_remote, "check_ssh", return_value=(True, ["ssh ok"])),
            mock.patch.object(
                preflight_remote,
                "check_dbus_env",
                return_value=(True, ["env ok"], {"DBUS_SESSION_BUS_ADDRESS": "dbus", "XDG_RUNTIME_DIR": "/run/user/502"}),
            ),
            mock.patch.object(preflight_remote, "check_mdbctl", return_value=(True, ["mdbctl ok"])),
            mock.patch.object(preflight_remote, "check_busctl", return_value=(True, ["busctl ok"])),
            mock.patch.object(preflight_remote, "check_telnet", return_value=(True, ["telnet ok"])),
            contextlib.redirect_stdout(stdout),
        ):
            rc = preflight_remote.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "preflight_remote")
        self.assertEqual(rc, 0)
        self.assertTrue(payload["overall_ok"])
        self.assertEqual(payload["overall_code"], "ok")
        self.assertEqual(payload["failure_count"], 0)
        self.assertEqual(payload["failed_checks"], [])
        self.assertEqual(
            payload["recommended_next_step"],
            "Continue with busctl_remote.py for object queries or collect_logs.py for log queries.",
        )
        self.assertEqual(payload["recommended_command"], self._expected_busctl_command())

    def test_preflight_json_reports_telnet_timeout_as_failed_check(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["preflight_remote.py", "--ip", "10.121.177.97", "--json"]),
            mock.patch.object(preflight_remote, "resolve_ssh_credentials", return_value={"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""}),
            mock.patch.object(preflight_remote, "resolve_telnet_credentials", return_value={"user": "Administrator", "password": "Admin@9000", "port": 23}),
            mock.patch.object(preflight_remote, "build_debug_dumper", return_value=None),
            mock.patch.object(preflight_remote, "check_ssh", return_value=(True, ["ssh ok"])),
            mock.patch.object(
                preflight_remote,
                "check_dbus_env",
                return_value=(True, ["env ok"], {"DBUS_SESSION_BUS_ADDRESS": "dbus", "XDG_RUNTIME_DIR": "/run/user/502"}),
            ),
            mock.patch.object(preflight_remote, "check_mdbctl", return_value=(True, ["mdbctl ok"])),
            mock.patch.object(preflight_remote, "check_busctl", return_value=(True, ["busctl ok"])),
            mock.patch.object(preflight_remote, "telnet_connect", side_effect=TimeoutError("timed out")),
            contextlib.redirect_stdout(stdout),
        ):
            rc = preflight_remote.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "preflight_remote")
        self.assertEqual(rc, 1)
        self.assertFalse(payload["overall_ok"])
        self.assertEqual(payload["failed_checks"], ["TELNET"])
        self.assertEqual(payload["checks"]["TELNET"]["code"], "telnet_unavailable")
        self.assertEqual(payload["checks"]["TELNET"]["lines"], ["timed out"])

    def test_preflight_runs_independent_remote_checks_concurrently(self) -> None:
        def delayed(result, delay: float):
            def inner(*_args, **_kwargs):
                time.sleep(delay)
                return result

            return inner

        stdout = io.StringIO()
        start = time.perf_counter()
        with (
            mock.patch.object(sys, "argv", ["preflight_remote.py", "--ip", "10.121.177.97", "--json"]),
            mock.patch.object(preflight_remote, "resolve_ssh_credentials", return_value={"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""}),
            mock.patch.object(preflight_remote, "resolve_telnet_credentials", return_value={"user": "Administrator", "password": "Admin@9000", "port": 23}),
            mock.patch.object(preflight_remote, "build_debug_dumper", return_value=None),
            mock.patch.object(preflight_remote, "check_ssh", side_effect=delayed((True, ["ssh ok"]), 0.18)),
            mock.patch.object(
                preflight_remote,
                "check_dbus_env",
                side_effect=delayed((True, ["env ok"], {"DBUS_SESSION_BUS_ADDRESS": "dbus", "XDG_RUNTIME_DIR": "/run/user/502"}), 0.18),
            ),
            mock.patch.object(preflight_remote, "check_mdbctl", side_effect=delayed((True, ["mdbctl ok"]), 0.18)),
            mock.patch.object(preflight_remote, "check_busctl", side_effect=delayed((True, ["busctl ok"]), 0.02)),
            mock.patch.object(preflight_remote, "check_telnet", side_effect=delayed((True, ["telnet ok"]), 0.18)),
            contextlib.redirect_stdout(stdout),
        ):
            rc = preflight_remote.main()
        duration = time.perf_counter() - start

        self.assertEqual(rc, 0)
        self.assertLess(duration, 0.55)

    def test_preflight_remote_checks_use_posix_login_shell_wrapper(self) -> None:
        with mock.patch.object(
            preflight_remote,
            "run_ssh",
            return_value=subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="ok", stderr=""),
        ) as run_ssh:
            preflight_remote.check_ssh(
                argparse.Namespace(ip="10.121.177.97", ssh_timeout=5),
                {"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""},
            )
            ssh_cmd = run_ssh.call_args.args[3]

            preflight_remote.check_mdbctl(
                argparse.Namespace(ip="10.121.177.97", ssh_timeout=5),
                {"user": "Administrator", "password": "Admin@9000", "port": 22, "identity_file": ""},
            )
            mdbctl_cmd = run_ssh.call_args.args[3]

        self.assertTrue(ssh_cmd.startswith("sh -lc "))
        self.assertNotIn("bash -ilc", ssh_cmd)
        self.assertTrue(mdbctl_cmd.startswith("sh -lc "))
        self.assertIn(". /etc/profile >/dev/null 2>&1;", mdbctl_cmd)
        self.assertNotIn("source /etc/profile", mdbctl_cmd)


class RoutingPressureCaseTests(unittest.TestCase):
    def test_routing_case_fixture_covers_core_paths(self) -> None:
        cases = json.loads(read_fixture("routing_cases.json"))
        expected_paths = {case["expected_path"] for case in cases}

        self.assertGreaterEqual(len(cases), 8)
        self.assertEqual(
            expected_paths,
            {
                "local-only",
                "ssh",
                "telnet",
                "ssh+telnet",
                "log-analyzer",
                "log-analyzer+debug",
                "route-away-developer",
            },
        )
        for case in cases:
            self.assertTrue(case["id"])
            self.assertTrue(case["prompt"])
            self.assertTrue(case["reason"])
            self.assertIn(case["expected_skill"], {"openubmc-debug", "openubmc-log-analyzer", "openubmc-developer"})
            self.assertTrue(case["expected_channels"])
            self.assertIsInstance(case["preferred_scripts"], list)
            self.assertIsInstance(case["forbidden_scripts"], list)

    def test_routing_reference_and_skill_link_cover_pressure_cases(self) -> None:
        case_doc = read_skill_file("references/routing-cases.md")
        skill_md = read_skill_file("SKILL.md")
        cases = json.loads(read_fixture("routing_cases.json"))

        self.assertIn("### routing pressure cases", case_doc.lower())
        self.assertIn("routing-cases.md", skill_md)
        for case in cases:
            self.assertIn(case["id"], case_doc)

    def test_skill_docs_require_notebooklm_background_parallel_usage(self) -> None:
        skill_md = read_skill_file("SKILL.md")
        notebooklm_md = read_skill_file("references/notebooklm.md")

        self.assertIn("NotebookLM", skill_md)
        self.assertIn("不要等待 NotebookLM 返回", skill_md)
        self.assertIn("preflight_remote.py", skill_md)
        self.assertIn("collect_logs.py", skill_md)

        self.assertIn("并行", notebooklm_md)
        self.assertIn("后台", notebooklm_md)
        self.assertIn("不要等待 NotebookLM 返回", notebooklm_md)
        self.assertIn("mdbctl", notebooklm_md)
        self.assertIn("busctl", notebooklm_md)


class ParallelLauncherTests(unittest.TestCase):
    def test_parallel_launcher_builds_lane_plan_with_optional_notebooklm(self) -> None:
        triage_parallel = load_script_module("triage_parallel")

        args = triage_parallel.parse_args(
            [
                "--ip",
                "10.121.177.97",
                "--keyword",
                "SensorSelInfo",
                "--service",
                "bmc.kepler.sensor",
                "--log",
                "framework.log",
                "--grep",
                "sensor scan failed",
                "--notebooklm-question",
                "SensorSelInfo belongs to which component?",
            ]
        )
        plan = triage_parallel.build_session_plan(args)

        self.assertEqual(plan["mode"], "manual")
        self.assertEqual([lane["name"] for lane in plan["lanes"]], ["local", "ssh", "telnet", "notebooklm"])
        self.assertIn("rg -n 'SensorSelInfo' /home/workspace/source/", plan["lanes"][0]["command"])
        self.assertIn("preflight_remote.py", plan["lanes"][1]["command"])
        self.assertIn("busctl_remote.py", plan["lanes"][1]["command"])
        self.assertIn("collect_logs.py", plan["lanes"][2]["command"])
        self.assertIn("ask_question.py", plan["lanes"][3]["command"])

    def test_parallel_launcher_can_emit_json(self) -> None:
        triage_parallel = load_script_module("triage_parallel")
        stdout = io.StringIO()

        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "triage_parallel.py",
                    "--ip",
                    "10.121.177.97",
                    "--keyword",
                    "SensorSelInfo",
                    "--json",
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            rc = triage_parallel.main()

        payload = json.loads(stdout.getvalue())
        assert_common_json_contract(self, payload, "triage_parallel")
        self.assertEqual(rc, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["code"], "ok")
        self.assertEqual(payload["request"]["ip"], "10.121.177.97")
        self.assertEqual(payload["result"]["lane_names"], ["local", "ssh", "telnet"])

    def test_parallel_launcher_can_issue_tmux_commands_when_available(self) -> None:
        triage_parallel = load_script_module("triage_parallel")
        plan = {
            "session_name": "openubmc-debug-10-121-177-97",
            "mode": "tmux",
            "lanes": [
                {"name": "local", "command": "echo local"},
                {"name": "ssh", "command": "echo ssh"},
                {"name": "telnet", "command": "echo telnet"},
            ],
        }
        calls: list[list[str]] = []

        def fake_run(cmd, check):
            calls.append(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        with (
            mock.patch.object(triage_parallel.shutil, "which", return_value="/usr/bin/tmux"),
            mock.patch.object(triage_parallel.subprocess, "run", side_effect=fake_run),
        ):
            triage_parallel.launch_tmux_session(plan)

        self.assertEqual(calls[0][:4], ["tmux", "new-session", "-d", "-s"])
        self.assertTrue(any(cmd[:2] == ["tmux", "new-window"] for cmd in calls[1:]))
        self.assertTrue(any(cmd[:2] == ["tmux", "send-keys"] for cmd in calls[1:]))

    def test_skill_docs_reference_parallel_launcher(self) -> None:
        skill_md = read_skill_file("SKILL.md")
        env_access_md = read_skill_file("references/env-access.md")

        self.assertIn("triage_parallel.py", skill_md)
        self.assertIn("triage_parallel.py", env_access_md)

    def test_env_access_documents_busctl_vs_mdbctl_usage_boundary(self) -> None:
        env_access_md = read_skill_file("references/env-access.md")

        self.assertIn("busctl vs mdbctl", env_access_md)
        self.assertIn("`mdbctl` 更适合", env_access_md)
        self.assertIn("`busctl` 更适合", env_access_md)
        self.assertIn("busctl --user monitor", env_access_md)
        self.assertIn("mdbctl attach", env_access_md)

    def test_env_access_consolidates_examples_around_current_cli_and_dump_notes(self) -> None:
        env_access_md = read_skill_file("references/env-access.md")

        self.assertEqual(env_access_md.count("`summary.json`"), 1)
        self.assertIn("--ssh-port 22 --ssh-user-env BMC_USER --ssh-password-env BMC_PASS", env_access_md)
        self.assertIn("--ssh-user-env BMC_USER --ssh-password-env BMC_PASS --json lsclass", env_access_md)
        self.assertNotIn("--port 22 --user-env BMC_USER --password-env BMC_PASS", env_access_md)
        self.assertNotIn("--user-env BMC_USER --password-env BMC_PASS --json lsclass", env_access_md)
        self.assertNotIn("NotebookLM 摘要", env_access_md)

    def test_skill_and_overview_repeat_same_mdbctl_busctl_entry_guidance(self) -> None:
        skill_md = read_skill_file("SKILL.md")
        overview_md = read_skill_file("references/overview.md")

        phrases = [
            "`mdbctl` 更适合 openUBMC 微组件对象调试",
            "`busctl` 更适合原始 D-Bus 观察和精确调用",
            "`mdbctl` 失败不代表对象面不可查",
        ]
        for phrase in phrases:
            self.assertIn(phrase, skill_md)
            self.assertIn(phrase, overview_md)

    def test_skill_prefers_mdbctl_first_and_requires_obsidian_debug_notes(self) -> None:
        skill_md = read_skill_file("SKILL.md")
        overview_md = read_skill_file("references/overview.md")
        note_template = read_skill_file("references/obsidian-debug-note-template.md")

        self.assertIn("远端对象查询：默认先试 `python scripts/mdbctl_remote.py --ip <ip> lsclass`", skill_md)
        self.assertNotIn(
            "远端对象查询：需要机器可读结果时，优先 `python scripts/busctl_remote.py --ip <ip> --action tree --service <service> --json`",
            skill_md,
        )
        self.assertIn("对象面默认先试 `mdbctl_remote.py`", overview_md)
        self.assertIn("/mnt/e/obsidian/openubmc/", skill_md)
        self.assertIn("排查思路", skill_md)
        self.assertIn("排查方法", skill_md)
        self.assertIn("obsidian-debug-note-template.md", skill_md)

        self.assertIn("## 排查思路", note_template)
        self.assertIn("## 排查方法", note_template)
        self.assertIn("## 关键证据", note_template)
        self.assertIn("## 结论", note_template)

    def test_skill_and_template_define_when_to_write_stage_summary(self) -> None:
        skill_md = read_skill_file("SKILL.md")
        note_template = read_skill_file("references/obsidian-debug-note-template.md")

        for phrase in ["阶段性总结", "已给出明确结论", "形成稳定方法", "被外部条件卡住"]:
            self.assertIn(phrase, skill_md)
            self.assertIn(phrase, note_template)


class UnifiedRemoteArgTests(unittest.TestCase):
    def test_busctl_and_mdbctl_accept_unified_ssh_flags(self) -> None:
        busctl_args = parse_with_argv(
            busctl_remote.parse_args,
            [
                "busctl_remote.py",
                "--ip",
                "10.121.177.97",
                "--ssh-port",
                "2222",
                "--ssh-user",
                "cli-user",
                "--ssh-user-env",
                "BMC_USER",
                "--ssh-password-env",
                "BMC_PASS",
                "--identity-file",
                "/tmp/test_id",
                "--print-env",
            ],
        )
        self.assertEqual(busctl_args.ssh_port, 2222)
        self.assertEqual(busctl_args.ssh_user, "cli-user")
        self.assertEqual(busctl_args.ssh_user_env, "BMC_USER")
        self.assertEqual(busctl_args.ssh_password_env, "BMC_PASS")
        self.assertEqual(busctl_args.ssh_identity_file, "/tmp/test_id")

        mdbctl_args = parse_with_argv(
            mdbctl_remote.parse_args,
            [
                "mdbctl_remote.py",
                "--ip",
                "10.121.177.97",
                "--port",
                "2200",
                "--user-env",
                "BMC_USER",
                "--password-env",
                "BMC_PASS",
                "--identity-file",
                "/tmp/test_id",
                "lsclass",
            ],
        )
        self.assertEqual(mdbctl_args.ssh_port, 2200)
        self.assertEqual(mdbctl_args.ssh_user_env, "BMC_USER")
        self.assertEqual(mdbctl_args.ssh_password_env, "BMC_PASS")
        self.assertEqual(mdbctl_args.ssh_identity_file, "/tmp/test_id")

    def test_collect_and_preflight_accept_unified_telnet_flags(self) -> None:
        collect_args = parse_with_argv(
            collect_logs.parse_args,
            [
                "collect_logs.py",
                "--ip",
                "10.121.177.97",
                "--telnet-port",
                "2323",
                "--telnet-user-env",
                "TEL_USER",
                "--telnet-password-env",
                "TEL_PASS",
            ],
        )
        self.assertEqual(collect_args.telnet_port, 2323)
        self.assertEqual(collect_args.telnet_user_env, "TEL_USER")
        self.assertEqual(collect_args.telnet_password_env, "TEL_PASS")

        preflight_args = parse_with_argv(
            preflight_remote.parse_args,
            [
                "preflight_remote.py",
                "--ip",
                "10.121.177.97",
                "--ssh-port",
                "2222",
                "--ssh-user-env",
                "BMC_USER",
                "--ssh-password-env",
                "BMC_PASS",
                "--ssh-identity-file",
                "/tmp/test_id",
                "--telnet-user-env",
                "TEL_USER",
                "--telnet-password-env",
                "TEL_PASS",
            ],
        )
        self.assertEqual(preflight_args.ssh_port, 2222)
        self.assertEqual(preflight_args.ssh_user_env, "BMC_USER")
        self.assertEqual(preflight_args.ssh_password_env, "BMC_PASS")
        self.assertEqual(preflight_args.ssh_identity_file, "/tmp/test_id")
        self.assertEqual(preflight_args.telnet_user_env, "TEL_USER")
        self.assertEqual(preflight_args.telnet_password_env, "TEL_PASS")

    def test_shared_env_resolver_prefers_explicit_env_over_defaults(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "_cli_common",
            SKILL_ROOT / "scripts" / "_cli_common.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with mock.patch.dict(module.os.environ, {"BMC_USER": "env-user", "BMC_PASS": "env-pass"}, clear=False):
            self.assertEqual(module.resolve_value("default-user", "BMC_USER", "SSH user"), "env-user")
            self.assertEqual(module.resolve_value("default-pass", "BMC_PASS", "SSH password"), "env-pass")

        with self.assertRaises(SystemExit):
            module.resolve_value("default-user", "MISSING_BMC_USER", "SSH user")


class DocumentationRegressionTests(unittest.TestCase):
    def test_obsidian_capture_happens_after_task_completion_not_mid_stream(self) -> None:
        skill_text = read_skill_file("SKILL.md")
        template_text = read_skill_file("references/obsidian-debug-note-template.md")
        overview_text = read_skill_file("references/overview.md")
        lesson_text = read_skill_file("references/lessons/2026-03-18-write-an-obsidian-debug-note-after-each-session.md")

        self.assertIn("任务完成后", skill_text)
        self.assertNotIn("每次排障结束后，都要把结论同步到 Obsidian 笔记", skill_text)
        self.assertIn("默认在任务完成后", template_text)
        self.assertIn("任务完成后", overview_text)
        self.assertIn("after task completion", lesson_text.lower())

    def test_obsidian_capture_happens_only_when_user_requests_it(self) -> None:
        skill_text = read_skill_file("SKILL.md")
        template_text = read_skill_file("references/obsidian-debug-note-template.md")
        overview_text = read_skill_file("references/overview.md")
        lesson_text = read_skill_file("references/lessons/2026-03-18-write-an-obsidian-debug-note-after-each-session.md")

        self.assertIn("由用户决定", skill_text)
        self.assertIn("用户明确要求", skill_text)
        self.assertIn("由用户决定", template_text)
        self.assertIn("用户明确要求", overview_text)
        self.assertIn("user explicitly asks", lesson_text.lower())


if __name__ == "__main__":
    unittest.main()
