"""Local accounts, expiring cookie sessions and per-user persistent data."""
import hashlib, hmac, json, secrets, sqlite3, time, re
from pathlib import Path
from http.cookies import SimpleCookie

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'private' / 'accounts.sqlite3'
FIELDS = ('edit', 'create', 'delete')

def connect():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def password_hash(password):
    if not isinstance(password, str) or not 10 <= len(password) <= 256:
        raise ValueError('密码长度应为 10–256 个字符')
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest

def verify(password, stored):
    try:
        salt, digest = stored.split(':')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, AttributeError): return False

def initialize():
    DB.parent.mkdir(mode=0o700, exist_ok=True)
    with connect() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0, permissions TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS state(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(user_id,key));
        ''')
        if not conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            password = secrets.token_urlsafe(18)
            conn.execute('INSERT INTO users(username,password,admin,permissions,created) VALUES(?,?,?,?,?)', ('admin',password_hash(password),1,json.dumps({'visible':None,'edit':True,'create':True,'delete':True}),time.time()))
            path = DB.parent / 'admin-initial-password.txt'
            path.write_text('账号：admin\n初始密码：' + password + '\n请登录后在账号菜单中修改密码。\n')
            path.chmod(0o600)
    DB.chmod(0o600)

def public_user(row):
    return {'id':row['id'], 'username':row['username'], 'admin':bool(row['admin']), 'permissions':json.loads(row['permissions'])}

def session_user(cookie):
    try:
        jar = SimpleCookie(); jar.load(cookie or '')
        token = jar['mykb_session'].value
    except (KeyError, TypeError): return None
    with connect() as conn:
        row=conn.execute('SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    return public_user(row) if row else None

def login(username, password):
    if not isinstance(username,str) or not isinstance(password,str) or len(password)>256: return None
    with connect() as conn:
        row=conn.execute('SELECT * FROM users WHERE username=?',(username.strip(),)).fetchone()
        # Perform password work even for unknown accounts.
        if not verify(password, row['password'] if row else '00'*16+':'+'00'*64): return None
        token=secrets.token_urlsafe(32)
        conn.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        conn.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],time.time()+7*86400))
    return token, public_user(row)

def logout(cookie):
    try:
        jar=SimpleCookie();jar.load(cookie or '')
        with connect() as conn: conn.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(jar['mykb_session'].value.encode()).hexdigest(),))
    except (KeyError, TypeError): pass

def visible(user, item):
    allowed=user['permissions'].get('visible')
    return user['admin'] or allowed is None or item['section']+'::'+item['category'] in allowed

def may(user, action): return user['admin'] or user['permissions'].get(action) is True

def normalize_permissions(value):
    if not isinstance(value,dict): raise ValueError('权限设置无效')
    allowed=value.get('visible')
    if allowed is not None and (not isinstance(allowed,list) or len(allowed)>2000 or any(not isinstance(v,str) or len(v)>200 for v in allowed)):
        raise ValueError('可见分类设置无效')
    return {'visible':allowed, **{key:value.get(key) is True for key in FIELDS}}

def manage(payload, actor):
    action=payload.get('action')
    with connect() as conn:
        if action=='create':
            username=payload.get('username','')
            if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_\-.]{3,40}', username): raise ValueError('用户名需为 3–40 位字母、数字、下划线、点或横线')
            try:
                conn.execute('INSERT INTO users(username,password,admin,permissions,created) VALUES(?,?,?,?,?)',(username,password_hash(payload.get('password')),int(payload.get('admin') is True),json.dumps(normalize_permissions(payload.get('permissions',{}))),time.time()))
            except sqlite3.IntegrityError: raise ValueError('用户名已存在')
        elif action in ('update','delete'):
            target=conn.execute('SELECT * FROM users WHERE id=?',(payload.get('id'),)).fetchone()
            if not target: raise ValueError('用户不存在')
            if target['id']==actor['id'] and (action=='delete' or not payload.get('admin',bool(target['admin']))): raise ValueError('不能删除或取消自己的管理员权限')
            if action=='delete': conn.execute('DELETE FROM users WHERE id=?',(target['id'],))
            else:
                conn.execute('UPDATE users SET admin=?,permissions=? WHERE id=?',(int(payload.get('admin') is True),json.dumps(normalize_permissions(payload.get('permissions',{}))),target['id']))
                if payload.get('password'):
                    conn.execute('UPDATE users SET password=? WHERE id=?',(password_hash(payload['password']),target['id']))
                    conn.execute('DELETE FROM sessions WHERE user_id=?',(target['id'],))
        else: raise ValueError('操作无效')
    return {'message':'用户设置已保存'}

def users():
    with connect() as conn: return [public_user(row) for row in conn.execute('SELECT * FROM users ORDER BY id')]

def read_state(user):
    with connect() as conn: return {row['key']:json.loads(row['value']) for row in conn.execute('SELECT key,value FROM state WHERE user_id=?',(user['id'],))}

def write_state(user,key,value):
    if key not in ('saved','savedTags','externalBookmarks','progress','last','legacyImported','accentTheme','learningOrder') and not re.fullmatch(r'draft\.[\w-]{1,100}',key or ''): raise ValueError('数据类型无效')
    if key == 'learningOrder':
        if not isinstance(value, list) or len(value) > 10000 or any(not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{16}', identity) for identity in value) or len(set(value)) != len(value):
            raise ValueError('学习路径顺序格式无效')
    if key=='accentTheme' and value not in ('blue','yellow'): raise ValueError('主题色无效')
    if key in ('saved','progress') and not isinstance(value,dict): raise ValueError('收藏或进度格式无效')
    if key=='savedTags':
        if not isinstance(value,dict) or len(value)>10000: raise ValueError('收藏标签格式无效')
        for item_id,tags in value.items():
            if not isinstance(item_id,str) or len(item_id)>200 or not item_id.startswith(('local:','external:')) or not isinstance(tags,list) or len(tags)>20 or any(not isinstance(tag,str) or not tag.strip() or len(tag)>30 for tag in tags): raise ValueError('收藏标签内容无效')
    if key=='externalBookmarks':
        if not isinstance(value,list) or len(value)>3000: raise ValueError('外链收藏格式无效')
        for item in value:
            if not isinstance(item,dict) or any(not isinstance(item.get(name,''),str) for name in ('id','url','title','description','image','favicon')): raise ValueError('外链内容无效')
            tags=item.get('tags',[])
            if not isinstance(tags,list) or len(tags)>20 or any(not isinstance(tag,str) or not tag.strip() or len(tag)>30 for tag in tags): raise ValueError('外链标签无效')
    if key.startswith('draft.') and not isinstance(value,str): raise ValueError('草稿格式无效')
    serialized=json.dumps(value,ensure_ascii=False)
    if len(serialized.encode())>800000: raise ValueError('个人数据过大，请下载备份')
    with connect() as conn:
        conn.execute('INSERT INTO state VALUES(?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value',(user['id'],key,serialized))
