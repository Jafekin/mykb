"""Cheap source change detection and atomic cache publication."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile


def source_signature(sections):
    digest = hashlib.sha256()
    for section, root, *_ in sections:
        root = Path(root)
        digest.update(str(root).encode())
        for path in sorted(root.rglob('*')):
            relative = path.relative_to(root)
            if any(part.startswith('.') for part in relative.parts) or not path.is_file():
                continue
            if path.suffix != '.md' and section != 'notes':
                continue
            stat = path.stat()
            digest.update(str((section, relative.as_posix(), stat.st_size, stat.st_mtime_ns)).encode())
    return digest.hexdigest()


def cache_matches(index, signature):
    try:
        return json.loads(Path(index).read_text())['sourceSignature'] == signature
    except (OSError, ValueError, KeyError):
        return False


@contextmanager
def build_lock(path):
    with Path(path).open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def atomic_json(path, value):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, separators=(',', ':'))
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
