import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from auto_sync import Sync, github_repository


def git(repo, *args):
    return subprocess.check_output(['git', '-c', 'core.quotepath=false', '-C', str(repo), *args], stderr=subprocess.DEVNULL).decode().strip()


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.remote = self.root / 'remote.git'
        self.repo = self.root / 'kb'
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(self.remote)], check=True)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.repo)], check=True)
        git(self.repo, 'config', 'user.name', 'Test')
        git(self.repo, 'config', 'user.email', 'test@example.invalid')
        (self.repo / '.gitignore').write_text('.DS_Store\n')
        (self.repo / 'article.md').write_text('# Initial\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'initial')
        git(self.repo, 'remote', 'add', 'origin', str(self.remote))
        git(self.repo, 'push', '-u', 'origin', 'main')
        self.worker = Sync(self.repo, str(self.remote))

    def tearDown(self):
        self.tmp.cleanup()

    def test_changes_and_deletion(self):
        (self.repo / 'article.md').unlink()
        (self.repo / '新增.md').write_text('# Added\n')
        with patch.object(self.worker, 'verify_private'):
            self.worker.sync()
        self.assertIsNone(self.worker.snapshot())
        self.assertEqual(git(self.repo, 'rev-parse', 'HEAD'), git(self.remote, 'rev-parse', 'main'))
        self.assertEqual(git(self.remote, 'ls-tree', '--name-only', 'main'), '.gitignore\n新增.md')

    def test_private_verification_blocks_push(self):
        before = git(self.remote, 'rev-parse', 'main')
        (self.repo / 'article.md').write_text('# Changed\n')
        with patch.object(self.worker, 'verify_private', side_effect=RuntimeError('private verification failed')):
            with self.assertRaises(RuntimeError):
                self.worker.sync()
        self.assertEqual(git(self.remote, 'rev-parse', 'main'), before)
        self.assertTrue(self.worker.pending())
        with patch.object(self.worker, 'verify_private'):
            self.worker.sync()
        self.assertFalse(self.worker.pending())

    def test_ignored_changes(self):
        (self.repo / '.DS_Store').write_text('cache')
        self.assertIsNone(self.worker.snapshot())

    def test_remote_changes_never_overwritten(self):
        other = self.root / 'other'
        subprocess.run(['git', 'clone', '-q', str(self.remote), str(other)], check=True)
        git(other, 'config', 'user.name', 'Other')
        git(other, 'config', 'user.email', 'other@example.invalid')
        (other / 'remote.md').write_text('Remote change')
        git(other, 'add', '-A'); git(other, 'commit', '-qm', 'remote'); git(other, 'push')
        remote_commit = git(self.remote, 'rev-parse', 'main')
        (self.repo / 'article.md').write_text('Local change')
        with patch.object(self.worker, 'verify_private'):
            with self.assertRaises(RuntimeError):
                self.worker.sync()
        self.assertEqual(git(self.remote, 'rev-parse', 'main'), remote_commit)
        self.assertEqual((self.repo / 'article.md').read_text(), 'Local change')
        self.assertTrue(self.worker.pending())

    def test_index_updates_before_network_failure(self):
        indexer = Mock()
        indexer.snapshot.return_value = 'changed'
        indexer.rebuild.side_effect = lambda: setattr(indexer.snapshot, 'return_value', None)
        self.worker.indexer = indexer
        (self.repo / 'article.md').write_text('Changed while offline')
        with patch.object(self.worker, 'verify_private', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                self.worker.sync()
            with self.assertRaises(RuntimeError):
                self.worker.sync()
        indexer.rebuild.assert_called_once()
        self.assertTrue(self.worker.pending())

    def test_index_updates_after_manual_commit(self):
        indexer = Mock()
        indexer.snapshot.return_value = 'changed'
        self.worker.indexer = indexer
        (self.repo / 'article.md').write_text('Manually committed update')
        git(self.repo, 'add', '-A'); git(self.repo, 'commit', '-qm', 'manual')
        self.assertIsNone(self.worker.snapshot())
        self.assertEqual(self.worker.index_snapshot(), 'changed')
        with patch.object(self.worker, 'verify_private'):
            self.worker.sync()
        indexer.rebuild.assert_called_once()
        self.assertFalse(self.worker.pending())

    def test_github_repository_urls(self):
        self.assertEqual(github_repository('https://github.com/owner/private.git'), 'owner/private')
        self.assertEqual(github_repository('git@github.com:owner/private.git'), 'owner/private')
        with self.assertRaises(ValueError):
            github_repository('https://example.com/owner/private.git')

    def test_debounce_detects_repeated_edits(self):
        (self.repo / 'article.md').write_text('One')
        first = self.worker.snapshot()
        (self.repo / 'article.md').write_text('Two')
        self.assertNotEqual(first, self.worker.snapshot())


if __name__ == '__main__':
    unittest.main()
