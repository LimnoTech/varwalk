"""No personal path, share or private address in a tracked text file.

A route is anything that locates a person's machine or a private
network: a home directory, a UNC path, an ``smb://`` URL, a private
IPv4 address. This file holds the patterns it forbids, so it is the one
tracked file the scan skips.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
THIS = Path(__file__).resolve().relative_to(REPO).as_posix()

PATTERNS = [
    (re.compile(r"/Users/(?!<)[A-Za-z0-9._-]+/"), "a macOS home directory"),
    (re.compile(r"/home/(?!<)[A-Za-z0-9._-]+/"), "a Linux home directory"),
    (
        re.compile(r"[A-Za-z]:\\+Users\\+(?!<)[A-Za-z0-9._-]+", re.I),
        "a Windows home directory",
    ),
    (re.compile(r"(?<![\w:\\])\\\\[A-Za-z0-9._-]+\\[A-Za-z0-9$._-]"), "a UNC path"),
    (re.compile(r"smb://[A-Za-z0-9]", re.I), "an smb:// URL"),
    (
        re.compile(
            r"(?<![\d.])(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\d.])"
        ),
        "a private IPv4 address",
    ),
]

SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".gif", ".parquet", ".pdf", ".zip"}


def tracked_files() -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    paths = [REPO / name for name in listing.split("\0") if name]
    return [
        p
        for p in paths
        if p.is_file()
        and p.suffix not in SKIP_SUFFIXES
        and p.relative_to(REPO).as_posix() != THIS
    ]


def scan(text: str) -> list[str]:
    return [label for pattern, label in PATTERNS if pattern.search(text)]


def test_the_patterns_catch_each_kind_of_route():
    assert scan("/Users/someone/data") == ["a macOS home directory"]
    assert scan("/home/someone/data") == ["a Linux home directory"]
    assert scan("C:\\Users\\someone\\data") == ["a Windows home directory"]
    assert scan("\\\\server\\share") == ["a UNC path"]
    assert scan("smb://server/share") == ["an smb:// URL"]
    assert scan("an `smb://` URL in prose") == []
    assert scan("host 10.1.2.3") == ["a private IPv4 address"]
    assert scan("/Users/<user>/data and 8.8.8.8") == []


def test_no_tracked_file_holds_a_route():
    found = []
    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label in scan(text):
            found.append(f"{path.relative_to(REPO).as_posix()}: {label}")
    assert found == []
