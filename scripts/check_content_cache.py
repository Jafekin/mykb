"""Verify index reuse and invalidation against a disposable knowledge base."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        scripts = self.root / 'scripts'
        scripts.mkdir()
        for name in ('config.py', 'import_content.py', 'content_cache.py', 'markdown_title.py', 'judge_tests.py'):
            shutil.copyfile(Path(__file__).parent / name, scripts / name)
        self.notes = self.root / 'knowledge-base/note'
        self.notes.mkdir(parents=True)
        self.article = self.notes / 'test.md'
        self.article.write_text('# Original\n\nText\n')
        self.asset = self.notes / 'assets/picture.txt'
        self.asset.parent.mkdir()
        self.asset.write_text('image fixture')
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('MYKB_') and key not in ('JAFEKIN_NOTES', 'LLMFORGE_CONTENT')}
        self.build()

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, *args):
        return json.loads(subprocess.check_output(['python3', str(self.root / 'scripts/import_content.py'), *args], env=self.env))

    def index(self):
        return json.loads((self.root / 'dist/data/index.json').read_text())

    def test_unchanged_reuses_cache(self):
        before = self.index()
        index_time = (self.root / 'dist/data/index.json').stat().st_mtime_ns
        self.assertTrue(self.build()['cached'])
        self.assertEqual(self.index(), before)
        self.assertEqual((self.root / 'dist/data/index.json').stat().st_mtime_ns, index_time)

    def test_add_edit_delete(self):
        self.article.write_text('# Updated\n')
        self.assertEqual(self.build()['documents'], 1)
        self.assertEqual(self.index()['items'][0]['title'], 'Updated')
        second = self.notes / 'second.md'
        second.write_text('# Second\n')
        self.assertEqual(self.build()['documents'], 2)
        second.unlink()
        self.assertEqual(self.build()['documents'], 1)
        self.assertEqual(len(list((self.root / 'dist/data/articles').glob('*.json'))), 1)

    def test_creation_time_survives_edits_and_migration(self):
        before = self.index()['items'][0]['createdAt']
        self.article.write_text('# Changed creation fixture\n')
        self.build()
        self.assertEqual(self.index()['items'][0]['createdAt'], before)
        old = self.index()
        old.pop('creationTimeVersion')
        old['items'][0].pop('createdAt')
        (self.root / 'dist/data/index.json').write_text(json.dumps(old))
        self.assertNotIn('cached', self.build())
        self.assertTrue(self.index()['items'][0]['createdAt'])

    def test_assets_and_hidden_cache(self):
        output = self.root / 'dist/note-files/assets/picture.txt'
        before = output.stat().st_mtime_ns
        self.article.write_text('# Modified\n')
        self.build()
        self.assertEqual(output.stat().st_mtime_ns, before)
        self.asset.write_text('new image data')
        self.build()
        self.assertEqual(output.read_text(), 'new image data')
        self.asset.unlink()
        self.build()
        self.assertFalse(output.exists())
        (self.notes / '.DS_Store').write_text('ignored')
        self.assertTrue(self.build()['cached'])

    def test_force_rebuild(self):
        before = self.index()['generatedAt']
        self.build('--force')
        self.assertNotEqual(self.index()['generatedAt'], before)

    def test_concurrent_builds(self):
        self.article.write_text('# Concurrent\n')
        command = ['python3', str(self.root / 'scripts/import_content.py')]
        first = subprocess.Popen(command, env=self.env, stdout=subprocess.PIPE)
        second = subprocess.Popen(command, env=self.env, stdout=subprocess.PIPE)
        outputs = [json.loads(first.communicate(timeout=20)[0]), json.loads(second.communicate(timeout=20)[0])]
        self.assertEqual(first.returncode, 0)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(sum(bool(item.get('cached')) for item in outputs), 1)
        self.assertEqual(self.index()['items'][0]['title'], 'Concurrent')


if __name__ == '__main__':
    unittest.main()
