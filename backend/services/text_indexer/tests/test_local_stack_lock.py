"""Launcher exclusion checks, without starting services or touching a database."""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('kill_owner', [False, True])
def test_duplicate_launcher_is_rejected_and_exit_releases_lock(tmp_path, kill_owner):
    helper = Path(__file__).resolve().parents[4] / 'tools/local_stack_lock.py'
    command = [sys.executable, str(helper), str(tmp_path / 'stack.lock')]
    owner = subprocess.Popen(
        command + ['bash', '-c', 'echo ready; read -r line'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert owner.stdout.readline().strip() == 'ready'
        duplicate = subprocess.run(command + ['true'], capture_output=True, text=True, timeout=5)
        assert duplicate.returncode == 1
        assert 'already running' in duplicate.stderr
        if kill_owner:
            owner.kill()
        else:
            owner.stdin.write('stop\n')
            owner.stdin.flush()
        owner.wait(timeout=5)
        recovered = subprocess.run(command + ['true'], capture_output=True, text=True, timeout=5)
        assert recovered.returncode == 0, recovered.stderr
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.communicate(timeout=5)
