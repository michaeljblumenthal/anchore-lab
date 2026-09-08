"""Clone a public git repository into a temp directory for scanning.

This is what makes "scan this repo" work fully in-cluster, without any
access to the caller's local filesystem: instead of pointing Syft at a
local path (which only the host-side stdio server can see -- see
tools.py's docstrings), the in-cluster server clones the repo itself, the
same way a CI runner would, then scans the clone. No hostPath mount, no
local filesystem dependency -- this is the pattern that survives moving
the cluster to a real cloud provider, where "the caller's laptop" isn't
reachable from a pod at all.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


class GitCloneError(RuntimeError):
    pass


@contextmanager
def cloned_repo(git_url: str, ref: str | None = None):
    """Shallow-clone git_url into a temp directory, yield the path, clean up after.

    Shallow (--depth 1) deliberately: this lab scans the current state of a
    repo, not its history, and a full clone of a large repo would be slow
    and mostly wasted work for that purpose.
    """
    tmpdir = tempfile.mkdtemp(prefix="git-scan-")
    try:
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd += ["--branch", ref]
        cmd += [git_url, tmpdir]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise GitCloneError(f"git clone failed for {git_url}: {proc.stderr.strip()[:2000]}")
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
