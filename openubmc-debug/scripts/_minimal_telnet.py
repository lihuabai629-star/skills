#!/usr/bin/env python3
"""Small Telnet client used by openUBMC helper scripts."""
from __future__ import annotations

import re
import socket
import time

IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250
SE = 240


class TelnetClient:
    """Minimal Telnet client with the small surface area this skill needs."""

    def __init__(self, host: str, port: int, timeout: int = 10) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buffer = bytearray()
        self._iac_pending = False
        self._iac_cmd: int | None = None
        self._subnegotiation = False
        self._subnegotiation_iac = False

    def _respond_to_negotiation(self, command: int, option: int) -> None:
        if command in (DO, DONT):
            self.sock.sendall(bytes([IAC, WONT, option]))
        elif command in (WILL, WONT):
            self.sock.sendall(bytes([IAC, DONT, option]))

    def _feed(self, data: bytes) -> bytes:
        cooked = bytearray()
        for byte in data:
            if self._subnegotiation:
                if self._subnegotiation_iac:
                    self._subnegotiation_iac = False
                    if byte == SE:
                        self._subnegotiation = False
                    elif byte == IAC:
                        continue
                    continue
                if byte == IAC:
                    self._subnegotiation_iac = True
                continue

            if self._iac_cmd is not None:
                self._respond_to_negotiation(self._iac_cmd, byte)
                self._iac_cmd = None
                continue

            if self._iac_pending:
                self._iac_pending = False
                if byte == IAC:
                    cooked.append(IAC)
                elif byte in (DO, DONT, WILL, WONT):
                    self._iac_cmd = byte
                elif byte == SB:
                    self._subnegotiation = True
                    self._subnegotiation_iac = False
                continue

            if byte == IAC:
                self._iac_pending = True
            else:
                cooked.append(byte)
        return bytes(cooked)

    def _recv_into_buffer(self, timeout: float) -> bool:
        self.sock.settimeout(max(timeout, 0.05))
        try:
            chunk = self.sock.recv(4096)
        except TimeoutError:
            return False
        if not chunk:
            return False
        self._buffer.extend(self._feed(chunk))
        return True

    def write(self, data: bytes) -> None:
        self.sock.sendall(data.replace(bytes([IAC]), bytes([IAC, IAC])))

    def read_until(self, expected: bytes, timeout: float = 20) -> bytes:
        deadline = time.time() + timeout
        while True:
            index = bytes(self._buffer).find(expected)
            if index != -1:
                end = index + len(expected)
                data = bytes(self._buffer[:end])
                del self._buffer[:end]
                return data
            remaining = deadline - time.time()
            if remaining <= 0 or not self._recv_into_buffer(remaining):
                data = bytes(self._buffer)
                self._buffer.clear()
                return data

    def expect(
        self,
        patterns: list[re.Pattern[bytes]],
        timeout: float = 5,
    ) -> tuple[int, re.Match[bytes] | None, bytes]:
        deadline = time.time() + timeout
        while True:
            current = bytes(self._buffer)
            for index, pattern in enumerate(patterns):
                match = pattern.search(current)
                if match:
                    end = match.end()
                    data = current[:end]
                    del self._buffer[:end]
                    return index, match, data
            remaining = deadline - time.time()
            if remaining <= 0 or not self._recv_into_buffer(remaining):
                data = bytes(self._buffer)
                self._buffer.clear()
                return -1, None, data

    def close(self) -> None:
        self.sock.close()
