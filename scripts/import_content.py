"""Build a portable, read-only snapshot; never modifies source knowledge bases."""
import os, re, json, hashlib, shutil, sys, subprocess
from pathlib import Path
from datetime import datetime, timezone
from judge_tests import JUDGEABLE
from config import CONTENT_ROOT, NOTES_ROOT
from markdown_title import article_title, article_excerpt
from content_cache import source_signature, cache_matches, build_lock, atomic_json

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
with build_lock(OUT / '.build.lock'):
    try:
        previous = json.loads((OUT / 'index.json').read_text())
    except (OSError, ValueError):
        previous = {}
    previous_items = {item['path']: item for item in previous.get('items', [])}
    migration_file = PROJECT / 'scripts' / 'learning-path-migration.json'
    learning_migrations = {
        record['newPath']: record
        for record in json.loads(migration_file.read_text())
    } if migration_file.exists() else {}
    signature = source_signature(SECTIONS)
    if previous.get('creationTimeVersion') == 2 and previous.get('excerptVersion') == 2 and '--force' not in sys.argv and cache_matches(OUT / 'index.json', signature) and (OUT / 'articles').is_dir():
        print(json.dumps({'cached': True, 'message': 'Source unchanged; using cached index'}))
        raise SystemExit(0)
    articles_dir = OUT / 'articles'
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
            migration = learning_migrations.get(rel) if section == 'learning' else None
            if migration:
                article_id = migration['id']
                paths[migration['path']] = article_id
            hashes[identity] = article_id; paths[rel] = article_id
            title = article_title(body, file.stem)
            category = file.parent.name if file.parent != root else '综合'
            # Retain existing access grants while the UI no longer groups paths.
            if migration:
                category = migration['category']
            def field(name):
                match = re.search(r'\*\*' + name + r'\*\*[：:]\s*([^\n]+)', body)
                return match.group(1).strip() if match else ''
            is_index = file.stem in ['目录', 'README', '00-导航', '99-完整索引']
            if is_index: title = category + ' · 目录'
            summary = re.sub(r'[#*>\[\]$|]', '', re.sub(r'https?://\S+', '', body))
            summary = ' '.join(summary.split())
            slug = next((key for key in JUDGEABLE if file.name.startswith(key + '-')), '') if section == 'problems' else ''
            file_stat = file.stat()
            old = previous_items.get(rel, {}) or migration or {}
            created_at = old.get('createdAt')
            if not created_at:
                birth = getattr(file_stat, 'st_birthtime', 0)
                if not birth:
                    try:
                        birth = float(subprocess.check_output(
                            ['stat', '-c', '%W', '--', str(file)], stderr=subprocess.DEVNULL))
                    except (OSError, ValueError, subprocess.CalledProcessError):
                        birth = 0
                created_at = (datetime.fromtimestamp(birth, timezone.utc).isoformat()
                              if birth > 0 else old.get('modifiedAt') or
                              datetime.fromtimestamp(file_stat.st_mtime, timezone.utc).isoformat())
            if section == 'papers':
                created_at = field('发布日期')
            item = dict(id=article_id, title=title, section=section, category=category, path=rel,
                        difficulty=field('难度'), date=field('发布日期') or field('发布时间'),
                        createdAt=created_at,
                        modifiedAt=datetime.fromtimestamp(file_stat.st_mtime, timezone.utc).isoformat(),
                        isIndex=is_index, judgeable=slug in JUDGEABLE,
                        excerpt=article_excerpt(body, prefer_summary=section == 'papers'), search=summary.lower())
            items.append(item)
            atomic_json(OUT / 'articles' / f'{article_id}.json', dict(id=article_id, body=body))
    note_files = PROJECT / 'dist' / 'note-files'
    valid_assets = set()
    for file in NOTE_SOURCE.rglob('*'):
        relative = file.relative_to(NOTE_SOURCE)
        if not file.is_file() or file.suffix.lower() == '.md' or any(part.startswith('.') for part in relative.parts): continue
        target = note_files / relative; valid_assets.add(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        source_stat = file.stat()
        if target.exists() and target.stat().st_size == source_stat.st_size and target.stat().st_mtime_ns == source_stat.st_mtime_ns:
            continue
        temporary = target.with_name('.' + target.name + '.cache-tmp')
        try:
            shutil.copy2(file, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    if note_files.exists():
        for asset in note_files.rglob('*'):
            if asset.is_file() and asset not in valid_assets: asset.unlink()
    manifest = dict(creationTimeVersion=2, excerptVersion=2, sourceSignature=signature, generatedAt=datetime.now(timezone.utc).isoformat(), sources=[str(SOURCE), str(NOTE_SOURCE)],
        items=items, paths=paths, aliases=aliases,
        sections=[dict(id=section, name=label, count=sum(item['section'] == section and not item['isIndex'] for item in items))
                  for section, _, label, _ in SECTIONS])
    atomic_json(OUT / 'index.json', manifest)
    valid_articles = {item['id'] + '.json' for item in items}
    for cached_article in articles_dir.glob('*.json'):
        if cached_article.name not in valid_articles: cached_article.unlink()
    print(json.dumps(dict(documents=len(items), duplicateFiles=aliases, sections=manifest['sections']), ensure_ascii=False, indent=2))
