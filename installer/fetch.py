"""Get a repository onto this machine: with git when there is one, else straight from GitHub.

Batocera has no git, so there a GitHub repository is downloaded as an archive.
A private one needs an access token, given as https://TOKEN@github.com/you/repo
or in the GITHUB_TOKEN environment variable.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class FetchError(Exception):
    pass


def is_url(location: str) -> bool:
    return "://" in location or location.startswith("git@")


def without_secrets(url: str) -> str:
    """The same address with any token removed, safe to print or remember."""
    if "://" not in url:
        return url
    parts = urlsplit(url)
    return urlunsplit(parts._replace(netloc=parts.hostname or ""))


def fetch(url: str, destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("git"):
        done = subprocess.run(["git", "clone", "--depth", "1", "--quiet", url, str(destination)], check=False)
        if done.returncode:
            raise FetchError(f"Could not download {without_secrets(url)} (is the address right, and do you have access?)")
        return destination
    return _github_archive(url, destination)


def _github_archive(url: str, destination: Path) -> Path:
    match = re.fullmatch(r"https://(?:([^@/]+)@)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?", url)
    if not match:
        raise FetchError("Without git, only https://github.com/... addresses can be downloaded. "
                         "Use a folder (a USB drive, say) instead.")
    token = match[1] or os.environ.get("GITHUB_TOKEN")
    request = urllib.request.Request(f"https://api.github.com/repos/{match[2]}/{match[3]}/tarball")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response, tarfile.open(fileobj=response, mode="r|gz") as archive:
            destination.mkdir(parents=True)
            archive.extractall(destination, filter="data")
    except OSError as problem:
        hint = "" if token else " If it is private, use https://TOKEN@github.com/... with an access token."
        raise FetchError(f"Could not download {without_secrets(url)}: {problem}.{hint}") from problem
    # GitHub wraps everything in one folder; lift its contents up.
    (wrapper,) = list(destination.iterdir())
    for item in wrapper.iterdir():
        item.rename(destination / item.name)
    wrapper.rmdir()
    return destination
