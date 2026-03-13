"""Test configuration — redirect core dirs to temp directory."""

import sys
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "mq" / "scripts"))

import pytest
import core


@pytest.fixture(autouse=True)
def isolated_mq_dirs(tmp_path):
    """Redirect all MQ directories to a temp directory for test isolation."""
    original = {
        "MQ_DIR": core.MQ_DIR,
        "REGISTRY_DIR": core.REGISTRY_DIR,
        "INBOX_DIR": core.INBOX_DIR,
        "DONE_DIR": core.DONE_DIR,
    }

    core.MQ_DIR = tmp_path / "mq"
    core.REGISTRY_DIR = core.MQ_DIR / "registry"
    core.INBOX_DIR = core.MQ_DIR / "inbox"
    core.DONE_DIR = core.MQ_DIR / "done"

    yield

    core.MQ_DIR = original["MQ_DIR"]
    core.REGISTRY_DIR = original["REGISTRY_DIR"]
    core.INBOX_DIR = original["INBOX_DIR"]
    core.DONE_DIR = original["DONE_DIR"]
