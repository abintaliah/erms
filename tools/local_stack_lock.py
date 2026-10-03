"""Hold a process-lifetime lock while executing the local stack launcher."""
import fcntl
import os
from pathlib import Path
import sys


def main():
    lock_path = Path(sys.argv[1])
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Never unlink this file: replacing its inode would allow two lock owners.
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('A local stack is already running. Stop it before starting another.', file=sys.stderr)
        os.close(descriptor)
        return 1
    os.set_inheritable(descriptor, True)
    os.environ['ERMS_LOCAL_STACK_LOCK_PID'] = str(os.getpid())
    os.execvp(sys.argv[2], sys.argv[2:])


if __name__ == '__main__':
    sys.exit(main())
