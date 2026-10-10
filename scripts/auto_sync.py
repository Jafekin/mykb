#!/usr/bin/env python3
"""Debounced, private-only Git pushes; never overwrites remote history."""
import fcntl
import hashlib
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import re
import shutil
from config import CONTENT_ROOT, setting, project_path
import time

PROJECT = Path(__file__).resolve().parent.parent
REPO = CONTENT_ROOT
REMOTE = str(setting('sync_remote', ''))
GH = str(setting('sync_gh', shutil.which('gh') or 'gh'))
BRANCH = str(setting('sync_branch', 'main'))
STATE = project_path(setting('sync_state_dir', str(PROJECT / 'private/auto-sync')))
POLL = float(setting('sync_poll_seconds', 5))
SETTLE = float(setting('sync_settle_seconds', 20))
RETRY = float(setting('sync_retry_seconds', 60))


def github_repository(remote):
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)', remote)
    if not match:
        raise ValueError('sync_remote must be a GitHub HTTPS or SSH repository URL')
    return match.group(1).removesuffix('.git')



class LocalIndex:
    def __init__(self):
        self.project = PROJECT
        sys.path.insert(0, str(self.project / 'scripts'))
        from config import CONTENT_ROOT, NOTES_ROOT
        from content_cache import source_signature, cache_matches
        self.signature = source_signature
        self.matches = cache_matches
        self.index = self.project / 'dist/data/index.json'
        self.sections = [(name, CONTENT_ROOT / folder) for name, folder in (
            ('interview', '面试题'), ('problems', '手撕题'), ('learning', '学习路径'), ('papers', '最新论文'))]
        self.sections.append(('notes', NOTES_ROOT))

    def snapshot(self):
        signature = self.signature(self.sections)
        return None if self.matches(self.index, signature) else signature

    def rebuild(self):
        result = subprocess.run([sys.executable, str(self.project / 'scripts/import_content.py')],
                                cwd=self.project, capture_output=True, timeout=180)
        if result.returncode:
            raise RuntimeError('Index rebuild failed: ' + result.stderr.decode(errors='replace')[-500:])
        logging.info('Updated local website index cache')


class Sync:
    def __init__(self, repo=REPO, remote=REMOTE, indexer=None, branch=BRANCH):
        self.repo = Path(repo)
        self.remote = remote
        self.indexer = indexer
        self.branch = branch

    def git(self, *args, check=True):
        result = subprocess.run(['git', '-C', str(self.repo), *args], capture_output=True,
                                env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'}, timeout=180)
        if check and result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace').strip() or 'Git command failed')
        return result

    def guard(self):
        if self.git('rev-parse', '--show-toplevel').stdout.decode().strip() != str(self.repo):
            raise RuntimeError('Knowledge base repository unavailable')
        if self.git('branch', '--show-current').stdout.strip() != self.branch.encode():
            raise RuntimeError('Automatic sync requires branch ' + self.branch)
        if self.git('remote', 'get-url', '--push', 'origin').stdout.decode().strip() != self.remote:
            raise RuntimeError('Unexpected push remote; automatic sync stopped')
        if self.git('ls-files', '-u').stdout:
            raise RuntimeError('Unresolved conflicts; automatic sync paused')
        git_dir = Path(self.git('rev-parse', '--absolute-git-dir').stdout.decode().strip())
        if any((git_dir / marker).exists() for marker in ('MERGE_HEAD', 'rebase-merge', 'rebase-apply', 'CHERRY_PICK_HEAD')):
            raise RuntimeError('Git operation in progress; automatic sync paused')

    def snapshot(self):
        self.guard()
        status = self.git('-c', 'status.renames=false', 'status', '--porcelain=v1', '-z', '--untracked-files=all').stdout
        if not status:
            return None
        digest = hashlib.sha256(status)
        for entry in status.split(b'\0'):
            if not entry:
                continue
            path = self.repo / os.fsdecode(entry[3:])
            try:
                stat = path.lstat()
                digest.update(str((stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)).encode())
            except FileNotFoundError:
                digest.update(b'deleted')
        return digest.hexdigest()

    def index_snapshot(self):
        return self.indexer.snapshot() if self.indexer else None

    def pending(self):
        result = self.git('rev-list', '--count', 'origin/' + self.branch + '..HEAD', check=False)
        return result.returncode != 0 or int(result.stdout.strip()) > 0

    def verify_private(self):
        result = subprocess.run([GH, 'api', 'repos/' + github_repository(self.remote), '--jq', '.private'],
                                capture_output=True, timeout=30)
        if result.returncode or result.stdout.strip() != b'true':
            raise RuntimeError('Cannot verify private repository; push skipped')

    def sync(self):
        self.guard()
        if self.index_snapshot():
            self.indexer.rebuild()
        if self.snapshot():
            self.git('add', '-A')
            if self.git('diff', '--cached', '--quiet', check=False).returncode == 1:
                self.git('commit', '-m', 'Auto-sync knowledge base ' + time.strftime('%Y-%m-%d %H:%M:%S'))
                logging.info('Committed knowledge base changes')
        if self.pending():
            self.verify_private()
            self.git('push', 'origin', self.branch)
            logging.info('Pushed to configured private repository')


def main():
    github_repository(REMOTE)
    if min(POLL, SETTLE, RETRY) <= 0:
        raise ValueError("Sync intervals must be positive")
    state = STATE
    state.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(), RotatingFileHandler(state / 'sync.log', maxBytes=1024 * 1024, backupCount=3)])
    with (state / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worker = Sync(indexer=LocalIndex())
        fingerprint = (None, None)
        changed_at = 0
        retry_at = 0
        logging.info('Watching knowledge base and index: poll %ss, settle %ss, retry %ss', POLL, SETTLE, RETRY)
        while True:
            now = time.monotonic()
            try:
                current = (worker.snapshot(), worker.index_snapshot())
                if current != fingerprint:
                    fingerprint = current
                    changed_at = now
                if now >= retry_at and ((current != (None, None) and now - changed_at >= SETTLE) or (current == (None, None) and worker.pending())):
                    worker.sync()
                    fingerprint = (None, None)
                    retry_at = 0
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
                if now >= retry_at:
                    logging.error('%s; keeping local changes, retry in %ss', error, RETRY)
                    retry_at = now + RETRY
            time.sleep(POLL)


if __name__ == '__main__':
    main()
