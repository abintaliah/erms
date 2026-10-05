"""Append missing literal defaults without changing existing local settings."""
import argparse
import os
from pathlib import Path
import re
import secrets

ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENT = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$')


def reconcile(template: Path, target: Path):
    original = target.read_bytes() if target.exists() else b''
    present = {
        match.group(1) for line in original.decode('utf-8').splitlines()
        if (match := ASSIGNMENT.match(line))
    }
    additions, added, skipped, comments = [], [], [], []
    for line in template.read_text(encoding='utf-8').splitlines():
        match = ASSIGNMENT.match(line)
        if not match:
            if line.strip().startswith('#'):
                comments.append(line)
            elif not line.strip():
                comments = []
            continue
        key, value = match.groups()
        if key not in present:
            if key == 'WEBUI_STORAGE_SECRET':
                line = key + '=' + secrets.token_urlsafe(48)
            elif re.search(r'replace[_-]|<[^>]+>', value, re.IGNORECASE):
                skipped.append(key)
                comments = []
                continue
            additions.extend(comments)
            additions.append(line)
            added.append(key)
            present.add(key)
        comments = []
    if additions:
        prefix = '\n' if original and not original.endswith(b'\n') else ''
        text = prefix + '\n# Missing settings added from .env.example.\n' + '\n'.join(additions) + '\n'
        # The launcher holds the stack lock. Append preserves existing bytes and
        # permissions; a newly created file is private even with a permissive umask.
        descriptor = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, 'ab') as stream:
            stream.write(text.encode('utf-8'))
    return added, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template', type=Path, default=ROOT / '.env.example')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    args = parser.parse_args()
    added, skipped = reconcile(args.template, args.env_file)
    print('Local environment: ' + ('added ' + ', '.join(added) if added else 'no missing settings.'))
    if skipped:
        print('Example credentials/placeholders were not copied; configure: ' + ', '.join(skipped))


if __name__ == '__main__':
    main()
