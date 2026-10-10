"""Build a portable, read-only snapshot; never modifies source knowledge bases."""
import os, re, json, hashlib, shutil
from pathlib import Path
from datetime import datetime, timezone
from judge_tests import JUDGEABLE
from config import CONTENT_ROOT, NOTES_ROOT

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = CONTENT_ROOT
NOTE_SOURCE = NOTES_ROOT
OUT = PROJECT / 'dist' / 'data'
SECTIONS = [
    ('interview', SOURCE / '面试题', '面试题', '02-面试题'),
    ('problems', SOURCE / '手撕题', '手撕题', '03-手撕题'),
    ('learning', SOURCE / '学习路径', '学习路径', '01-学习路径'),
    ('papers', SOURCE / '最新论文', '最新论文', '04-论文'),
    ('notes', NOTE_SOURCE, 'Note', 'notes'),
]
if not SOURCE.is_dir():
    if (OUT / 'index.json').exists():
        print('MyKB source unavailable: preserving bundled content snapshot.')
        raise SystemExit(0)
    raise SystemExit(f'Knowledge base not found: {SOURCE}')
if not NOTE_SOURCE.is_dir(): raise SystemExit(f'Notes folder not found: {NOTE_SOURCE}')
OUT.mkdir(parents=True, exist_ok=True)
articles_dir = OUT / 'articles'
if articles_dir.exists(): shutil.rmtree(articles_dir)
articles_dir.mkdir(exist_ok=True)
items, paths, hashes, aliases = [], {}, {}, 0
for section, root, label, prefix in SECTIONS:
    for file in sorted(root.rglob('*.md')):
        relative = file.relative_to(root)
        if file.name.startswith('._') or any(part.startswith('.') for part in relative.parts): continue
        body = file.read_text(encoding='utf-8'); rel = f'{prefix}/{relative.as_posix()}'
        identity = hashlib.sha256(body.encode()).hexdigest()
        if identity in hashes:
            paths[rel] = hashes[identity]; aliases += 1; continue
        article_id = hashlib.sha256(rel.encode()).hexdigest()[:16]
        hashes[identity] = article_id; paths[rel] = article_id
        title_match = re.search(r'^#\s+(.+)', body, re.M)
        frontmatter_title = re.search(r'^---\s*\n[\s\S]*?^title:\s*(.+?)\s*$[\s\S]*?^---', body, re.M)
        title = title_match.group(1).strip() if title_match else frontmatter_title.group(1).strip() if frontmatter_title else file.stem
        category = file.parent.name if file.parent != root else '综合'
        def field(name):
            match = re.search(r'\*\*' + name + r'\*\*[：:]\s*([^\n]+)', body)
            return match.group(1).strip() if match else ''
        is_index = file.stem in ['目录', 'README', '00-导航', '99-完整索引']
        if is_index: title = category + ' · 目录'
        summary = re.sub(r'[#*>\[\]$|]', '', re.sub(r'https?://\S+', '', body))
        summary = ' '.join(summary.split())
        slug = next((key for key in JUDGEABLE if file.name.startswith(key + '-')), '') if section == 'problems' else ''
        item = dict(id=article_id, title=title, section=section, category=category, path=rel,
                    difficulty=field('难度'), date=field('发布日期') or field('发布时间'),
                    modifiedAt=datetime.fromtimestamp(file.stat().st_mtime, timezone.utc).isoformat(),
                    isIndex=is_index, judgeable=slug in JUDGEABLE,
                    excerpt=summary[len(title):].strip()[:180], search=summary.lower())
        items.append(item)
        (OUT / 'articles' / f'{article_id}.json').write_text(json.dumps(dict(id=article_id, body=body), ensure_ascii=False))
note_files = PROJECT / 'dist' / 'note-files'
if note_files.exists(): shutil.rmtree(note_files)
for file in NOTE_SOURCE.rglob('*'):
    relative = file.relative_to(NOTE_SOURCE)
    if not file.is_file() or file.suffix.lower() == '.md' or any(part.startswith('.') for part in relative.parts): continue
    target = note_files / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(file, target)
manifest = dict(generatedAt=datetime.now(timezone.utc).isoformat(), sources=[str(SOURCE), str(NOTE_SOURCE)],
    items=items, paths=paths, aliases=aliases,
    sections=[dict(id=section, name=label, count=sum(item['section'] == section and not item['isIndex'] for item in items))
              for section, _, label, _ in SECTIONS])
(OUT / 'index.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')))
print(json.dumps(dict(documents=len(items), duplicateFiles=aliases, sections=manifest['sections']), ensure_ascii=False, indent=2))
