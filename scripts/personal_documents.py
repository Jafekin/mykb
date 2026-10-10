"""Owner-scoped documents stored outside the shared knowledge base."""
import hashlib
import re
import secrets
from datetime import datetime, timezone
import accounts


def initialize():
    with accounts.connect() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS personal_documents(
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL, category TEXT NOT NULL, body TEXT NOT NULL,
            created TEXT NOT NULL, modified TEXT NOT NULL)''')


def now():
    return datetime.now(timezone.utc).isoformat()


def revision(body):
    return hashlib.sha256(body.encode()).hexdigest()


def item(row):
    text = re.sub(r'[#*`>\[\]]', '', row['body'])
    return dict(id=row['id'], section='saved', category=row['category'], title=row['title'],
                personal=True, excerpt=text[:180], search=row['title']+' '+row['category']+' '+text,
                createdAt=row['created'], modifiedAt=row['modified'], path='', difficulty='')


def list_items(user):
    with accounts.connect() as conn:
        return [item(row) for row in conn.execute('SELECT * FROM personal_documents WHERE user_id=? ORDER BY created DESC', (user['id'],))]


def read(user, identity):
    with accounts.connect() as conn:
        row = conn.execute('SELECT * FROM personal_documents WHERE user_id=? AND id=?', (user['id'], identity)).fetchone()
    if not row:
        return 404, {'message': '文档不存在'}
    return 200, {**item(row), 'body': row['body'], 'revision': revision(row['body']), 'copies': 1}


def validate_body(body):
    if not isinstance(body, str) or not body.strip():
        raise ValueError('请填写文档正文')
    if len(body.encode()) > 1024*1024:
        raise ValueError('Markdown 超过 1 MiB 限制')


def create(user, payload):
    title, category, body = payload.get('title'), payload.get('category', ''), payload.get('body')
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
        raise ValueError('标题需为 1–120 个字符')
    if not isinstance(category, str) or len(category.strip()) > 80:
        raise ValueError('分类不能超过 80 个字符')
    validate_body(body)
    body = '# '+title.strip()+'\n\n'+body
    identity, timestamp = 'personal-'+secrets.token_hex(16), now()
    with accounts.connect() as conn:
        conn.execute('INSERT INTO personal_documents VALUES(?,?,?,?,?,?,?)',
                     (identity, user['id'], title.strip(), category.strip() or '个人文档', body, timestamp, timestamp))
    return 201, {'ok': True, 'id': identity, 'message': '个人文档已创建，仅你可见'}


def change(user, identity, payload, delete=False):
    if not delete:
        validate_body(payload.get('body'))
    with accounts.connect() as conn:
        # Serialize revision checks and writes so concurrent edits cannot overwrite each other.
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM personal_documents WHERE user_id=? AND id=?', (user['id'], identity)).fetchone()
        if not row:
            return 404, {'message': '文档不存在'}
        if payload.get('revision') != revision(row['body']):
            return 409, {'message': '文档已发生变化，请刷新后重试'}
        if delete:
            conn.execute('DELETE FROM personal_documents WHERE user_id=? AND id=?', (user['id'], identity))
        else:
            conn.execute('UPDATE personal_documents SET body=?,modified=? WHERE user_id=? AND id=?',
                         (payload['body'], now(), user['id'], identity))
    return 200, {'ok': True, 'id': identity, 'message': '个人文档已删除' if delete else '个人文档已保存'}
