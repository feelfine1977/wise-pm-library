import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import wise  # noqa: E402


@pytest.fixture
def p2p_norm():
    return wise.running_p2p_norm()


@pytest.fixture
def p2p_log():
    return wise.running_p2p_log()


@pytest.fixture
def p2p_result(p2p_log, p2p_norm):
    return wise.score(p2p_log, p2p_norm)
