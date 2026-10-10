"""Seed a new knowledge base with original examples without overwriting files."""
import shutil
from config import PROJECT, CONTENT_ROOT, NOTES_ROOT

for name in ('面试题','手撕题','学习路径','最新论文','note'):
    target = NOTES_ROOT if name == 'note' else CONTENT_ROOT / name
    target.mkdir(parents=True, exist_ok=True)
    for source in (PROJECT / 'examples' / name).rglob('*.md'):
        dest = target / source.relative_to(PROJECT / 'examples' / name)
        if dest.exists(): continue
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
print('Knowledge base initialized; existing documents preserved.')
