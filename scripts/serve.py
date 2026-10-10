"""Internal static server and sandboxed Python judge."""
import argparse, collections, hashlib, json, os, re, resource, shutil, sys, subprocess, tempfile, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, unquote, urljoin, parse_qs
import posixpath
import gzip
from http_compression import accepts_gzip
import accounts

from judge_tests import TESTS
from link_metadata import fetch_link_metadata
from config import CONTENT_ROOT, NOTES_ROOT, HOST, PORT, SITE_NAME, SITE_LOGO

CONTENT_SOURCE = CONTENT_ROOT
NOTES_SOURCE = NOTES_ROOT
SECTION_SOURCES = {
    "interview": (CONTENT_SOURCE / "面试题", "02-面试题"),
    "problems": (CONTENT_SOURCE / "手撕题", "03-手撕题"),
    "learning": (CONTENT_SOURCE / "学习路径", "01-学习路径"),
    "papers": (CONTENT_SOURCE / "最新论文", "04-论文"),
    "notes": (NOTES_SOURCE, "notes"),
}
EDIT_LOCK = threading.Lock()

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "dist"
VENV = PROJECT / ".judge-venv"
INDEX = ROOT / "data" / "index.json"
MAX_SOURCE = 64 * 1024
MAX_OUTPUT = 64 * 1024
TIMEOUT = 8
CONCURRENCY = threading.BoundedSemaphore(2)
RATE_LOCK = threading.Lock()
RATE = collections.defaultdict(collections.deque)

def load_problems():
    data = json.loads(INDEX.read_text())
    return {item["id"]: item for item in data["items"] if item["section"] == "problems"}

PROBLEMS = load_problems()
PROBLEMS_REVISION = INDEX.stat().st_mtime_ns
PROBLEMS_LOCK = threading.Lock()

def cached_problems():
    global PROBLEMS, PROBLEMS_REVISION
    with PROBLEMS_LOCK:
        revision = INDEX.stat().st_mtime_ns
        if revision != PROBLEMS_REVISION:
            PROBLEMS = load_problems()
            PROBLEMS_REVISION = revision
        return PROBLEMS

def slug_for(item):
    name = Path(item["path"]).name
    return next((key for key in TESTS if name.startswith(key + "-")), "")

def limited():
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024, 256 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    os.umask(0o077)

def runner_source(source, tests):
    return f'''import contextlib, io, json, sys, traceback
+class LimitedIO(io.StringIO):
+    def write(self, s):
+        if self.tell() + len(s) > {MAX_OUTPUT}:
+            raise RuntimeError("输出超过 {MAX_OUTPUT // 1024} KiB 限制")
+        return super().write(s)
+output = LimitedIO()
+def check(value, message="答案不正确"):
+    if not bool(value): raise AssertionError(message)
+def check_close(got, expected, atol=1e-6, rtol=1e-5):
+    import torch
+    if not torch.allclose(got, expected, atol=atol, rtol=rtol):
+        raise AssertionError(f"数值不匹配；得到 {{got}}，期望 {{expected}}")
+try:
+    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
+        exec(compile({source!r}, "<submission>", "exec"), globals(), globals())
+        import torch
+        exec(compile({tests!r}, "<hidden-tests>", "exec"), globals(), globals())
+    result={{"status":"accepted","message":"全部隐藏测试通过","output":output.getvalue()}}
+except AssertionError as e:
+    result={{"status":"wrong_answer","message":str(e) or "隐藏测试未通过","output":output.getvalue()}}
+except BaseException as e:
+    result={{"status":"runtime_error","message":f"{{type(e).__name__}}: {{e}}","output":output.getvalue()}}
+print("__JUDGE_RESULT__"+json.dumps(result,ensure_ascii=False))
+'''.replace("\n+", "\n")

def source_path_for(item):
    section = item.get("section")
    if section not in SECTION_SOURCES:
        raise ValueError("此内容不可编辑")
    root, prefix = SECTION_SOURCES[section]
    path = item.get("path", "")
    if not path.startswith(prefix + "/"):
        raise ValueError("内容路径无效")
    target = (root / path.removeprefix(prefix + "/")).resolve()
    root = root.resolve()
    if target.suffix.lower() != ".md" or root not in target.parents:
        raise ValueError("内容路径无效")
    return target

def save_article(article_id, body, revision):
    if not isinstance(body, str) or not body.strip():
        return 400, {"message": "Markdown 不能为空"}
    if len(body.encode("utf-8")) > 1024 * 1024:
        return 413, {"message": "Markdown 超过 1 MiB 限制"}
    with EDIT_LOCK:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
        item = next((entry for entry in data["items"] if entry["id"] == article_id), None)
        if not item:
            return 404, {"message": "文章不存在"}
        try:
            target = source_path_for(item)
        except ValueError as error:
            return 400, {"message": str(error)}
        if not target.is_file():
            return 404, {"message": "源 Markdown 文件不存在"}
        temporary = None
        try:
            original = target.read_bytes()
            if revision != hashlib.sha256(original).hexdigest():
                return 409, {"message": "源文件已被其他窗口或本地编辑器修改，请重新打开文章后再保存"}
            backup = PROJECT / "content-backups" / article_id / (str(time.time_ns()) + ".md")
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(original)
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".jafekin-", delete=False) as handle:
                temporary = Path(handle.name)
            shutil.copymode(target, temporary)
            temporary.write_text(body, encoding="utf-8")
            os.replace(temporary, target)
            subprocess.run([sys.executable, str(PROJECT / "scripts" / "import_content.py")], cwd=PROJECT, check=True, timeout=60, capture_output=True, text=True)
            global PROBLEMS
            PROBLEMS = load_problems()
        except OSError as error:
            if temporary: temporary.unlink(missing_ok=True)
            return 500, {"message": "无法保存 Markdown：" + str(error)}
        except subprocess.TimeoutExpired:
            if temporary: temporary.unlink(missing_ok=True)
            return 503, {"message": "重建索引超时，请稍后刷新页面"}
        except subprocess.CalledProcessError as error:
            if temporary: temporary.unlink(missing_ok=True)
            return 500, {"message": "Markdown 已保存，但索引重建失败：" + (error.stderr[-160:] or "未知错误")}
        updated = json.loads(INDEX.read_text(encoding="utf-8"))
        return 200, {"ok": True, "id": updated["paths"].get(item["path"], article_id), "message": "已保存到源文件并更新索引"}

def rebuild_index():
    if not EDIT_LOCK.acquire(blocking=False):
        return 409, {"message": "正在保存文档或重建索引，请稍后重试"}
    try:
        if not all(root.is_dir() for root, _ in SECTION_SOURCES.values()):
            return 503, {"message": "知识库源目录不可用，无法重建索引"}
        subprocess.run([sys.executable, str(PROJECT / "scripts" / "import_content.py"), "--force"], cwd=PROJECT, check=True, timeout=180, capture_output=True, text=True)
        global PROBLEMS
        PROBLEMS = load_problems()
        data = json.loads(INDEX.read_text(encoding="utf-8"))
        return 200, {"ok": True, "message": "索引已重建", "documents": len(data["items"]), "sections": data["sections"]}
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return 503, {"message": "索引重建失败，请检查源目录和服务日志后重试"}
    finally:
        EDIT_LOCK.release()

def delete_article(article_id, revision, copies):
    with EDIT_LOCK:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
        item = next((entry for entry in data["items"] if entry["id"] == article_id), None)
        if not item:
            return 404, {"message": "文章不存在或已删除"}
        aliases = [path for path, identity in data["paths"].items() if identity == article_id]
        if copies != len(aliases):
            return 409, {"message": "文档副本数量已变化，请重新确认删除"}
        trash = PROJECT / "content-trash" / (str(time.time_ns()) + "-" + article_id)
        records = []
        moved = []
        try:
            for path in aliases:
                section = next((key for key, (_, prefix) in SECTION_SOURCES.items() if path.startswith(prefix + "/")), None)
                target = source_path_for({"section": section, "path": path})
                if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != revision:
                    return 409, {"message": "源文档或重复副本已发生变化，请刷新后再删除"}
                records.append({"source": str(target), "trash": str(trash / "files" / path)})
            trash.mkdir(parents=True)
            (trash / "manifest.json").write_text(json.dumps({"title": item["title"], "id": article_id, "files": records}, ensure_ascii=False, indent=2), encoding="utf-8")
            for record in records:
                destination = Path(record["trash"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(record["source"], destination)
                moved.append(record)
            subprocess.run([sys.executable, str(PROJECT / "scripts" / "import_content.py")], cwd=PROJECT, check=True, timeout=60, capture_output=True, text=True)
            global PROBLEMS
            PROBLEMS = load_problems()
        except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            for record in reversed(moved):
                shutil.move(record["trash"], record["source"])
            if moved:
                subprocess.run([sys.executable, str(PROJECT / "scripts" / "import_content.py")], cwd=PROJECT, timeout=60, capture_output=True)
            return 500, {"message": "删除失败，已恢复源文档：" + str(error)}
        return 200, {"ok": True, "message": "文档已移入回收目录", "files": len(records), "trash": str(trash)}

def create_article(payload):
    section = payload.get("section")
    title = payload.get("title")
    category = payload.get("category", "")
    body = payload.get("body")
    if not isinstance(section, str) or section not in SECTION_SOURCES:
        return 400, {"message": "请选择有效栏目"}
    if not isinstance(title, str) or not title.strip() or len(title) > 120:
        return 400, {"message": "请填写标题，最多 120 个字符"}
    title = title.strip()
    if not isinstance(category, str) or len(category) > 80:
        return 400, {"message": "分类最多 80 个字符"}
    category = category.strip()
    for name in [title, category]:
        if name and (name.startswith('.') or name.endswith('.') or re.search(r'[\\/:*?"<>|\x00-\x1f\x7f]', name)):
            return 400, {"message": "标题和分类不能包含路径符号、控制字符或以点开头/结尾"}
    if title in ["目录", "README", "00-导航", "99-完整索引"]:
        return 400, {"message": "此标题用于知识库目录，请换一个文档标题"}
    if not isinstance(body, str) or not body.strip():
        return 400, {"message": "请填写文档正文"}
    content = "# " + title + "\n\n" + body.strip() + "\n"
    if len(content.encode("utf-8")) > 1024 * 1024:
        return 413, {"message": "文档超过 1 MiB 限制"}
    with EDIT_LOCK:
        root, prefix = SECTION_SOURCES[section]
        relative = Path(category) / (title + ".md") if category else Path(title + ".md")
        try:
            target = source_path_for({"section": section, "path": prefix + "/" + relative.as_posix()})
            if not root.is_dir():
                return 503, {"message": "知识库源目录不可用"}
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as handle:
                handle.write(content)
            subprocess.run([sys.executable, str(PROJECT / "scripts" / "import_content.py")], cwd=PROJECT, check=True, timeout=60, capture_output=True, text=True)
            global PROBLEMS
            PROBLEMS = load_problems()
            updated = json.loads(INDEX.read_text(encoding="utf-8"))
            article_id = updated["paths"][prefix + "/" + relative.as_posix()]
        except FileExistsError:
            return 409, {"message": "此分类下已有同名文档，请更换标题"}
        except (ValueError, OSError) as error:
            return 400, {"message": "创建失败：" + str(error)}
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return 503, {"message": "源文件已创建，但索引更新失败，请稍后重建索引"}
        return 201, {"ok": True, "id": article_id, "message": "文档已创建并保存到源目录"}

def run_judge(problem_id, source):
    item = cached_problems().get(problem_id)
    if not item:
        return 404, {"status":"invalid_problem","message":"题目不存在"}
    slug = slug_for(item)
    if slug not in TESTS:
        return 400, {"status":"not_supported","message":"这道题尚未配置自动评测"}
    if not isinstance(source, str) or not source.strip():
        return 400, {"status":"invalid_source","message":"代码不能为空"}
    if len(source.encode()) > MAX_SOURCE:
        return 413, {"status":"invalid_source","message":"代码超过 64 KiB 限制"}
    if not (VENV / 'bin' / 'python3').is_file() or not shutil.which('bwrap') or not shutil.which('systemd-run'):
        return 503, {'status':'unavailable','message':'评测环境未配置；请安装隔离运行依赖后启用'}
    if not CONCURRENCY.acquire(blocking=False):
        return 429, {"status":"busy","message":"评测队列繁忙，请稍后重试"}
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="mykb-judge-") as tmp:
            runner = Path(tmp) / "runner.py"
            runner.write_text(runner_source(source, TESTS[slug]))
            command = [
                "systemd-run", "--user", "--scope", "--quiet", "-p", "TasksMax=64", "-p", "MemoryMax=2G",
                "bwrap", "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-net", "--unshare-uts",
                "--ro-bind", "/usr", "/usr", "--ro-bind", "/sys", "/sys", "--symlink", "usr/bin", "/bin",
                "--symlink", "usr/lib", "/lib", "--proc", "/proc", "--dev", "/dev",
                "--ro-bind", str(VENV), "/runtime", "--dir", "/work",
                "--ro-bind", str(runner), "/work/runner.py", "--chdir", "/work",
                "--tmpfs", "/tmp", "--setenv", "HOME", "/tmp",
                "--setenv", "PYTHONPATH", "", "--setenv", "TORCH_HOME", "/tmp",
                "/runtime/bin/python3", "-I", "/work/runner.py",
            ]
            with tempfile.TemporaryFile() as output:
                try:
                    proc = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=output,
                                          stderr=subprocess.STDOUT, timeout=TIMEOUT,
                                          preexec_fn=limited, check=False)
                except subprocess.TimeoutExpired:
                    return 200, {"status":"time_limit","message":f"执行超过 {TIMEOUT} 秒","durationMs":round((time.monotonic()-started)*1000)}
                output.seek(0)
                text = output.read(MAX_OUTPUT).decode("utf-8", "replace")
            marker = "__JUDGE_RESULT__"
            lines = [line[len(marker):] for line in text.splitlines() if line.startswith(marker)]
            if not lines:
                duration = round((time.monotonic()-started)*1000)
                if proc.returncode in (-9, 137) and duration >= 4500:
                    return 200, {"status":"time_limit","message":"执行超过 CPU 时间限制","durationMs":duration}
                message = text[-2000:].strip() or f"评测进程异常退出（code {proc.returncode}）"
                return 200, {"status":"runtime_error","message":message,"durationMs":duration}
            result = json.loads(lines[-1])
            result["durationMs"] = round((time.monotonic()-started)*1000)
            result["output"] = result.get("output","")[-MAX_OUTPUT:]
            return 200, result
    finally:
        CONCURRENCY.release()

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(ROOT),**kwargs)

    def client_allowed(self):
        now=time.monotonic(); ip=self.client_address[0]
        with RATE_LOCK:
            queue=RATE[ip+ ("login" if self.request_path()=="/api/auth/login" else "actions")]
            while queue and queue[0] < now-60: queue.popleft()
            if len(queue) >= (12 if self.request_path()=="/api/auth/login" else 60): return False
            queue.append(now); return True

    def json_response(self, status, payload):
        body=json.dumps(payload,ensure_ascii=False).encode()
        compressed = len(body) >= 1024 and accepts_gzip(self.headers.get('Accept-Encoding'))
        if compressed: body = gzip.compress(body, compresslevel=4)
        self.send_response(status)
        if compressed: self.send_header('Content-Encoding', 'gzip')
        self.send_header('Vary', 'Accept-Encoding')
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(body)

    def request_path(self):
        return '/' + posixpath.normpath(unquote(urlsplit(self.path).path)).lstrip('/')

    def require_user(self):
        user=accounts.session_user(self.headers.get('Cookie'))
        if not user: self.json_response(401, {"message":"请先登录"})
        return user

    def content_index(self, user, summary=False):
        data=json.loads(INDEX.read_text(encoding='utf-8'))
        data['items']=[item for item in data['items'] if accounts.visible(user,item)]
        if summary:
            data['items']=[{key:value for key,value in item.items() if key != 'search'} for item in data['items']]
        ids={item['id'] for item in data['items']}
        data['paths']={key:value for key,value in data['paths'].items() if value in ids}
        if not user['admin']:data['sources']=[]
        if 'sections' in data:
            data['sections']=[{**section,'count':sum(item['section']==section['id'] and not item.get('isIndex') for item in data['items'])} for section in data['sections']]
        return data

    def allowed_article(self,user,article_id):
        return next((item for item in self.content_index(user)['items'] if item['id']==article_id),None)

    def do_POST(self):
        path = self.request_path()
        if path.startswith("/api/"):
            origin = self.headers.get("Origin")
            if self.headers.get("Sec-Fetch-Site") == "cross-site" or (origin and urlsplit(origin).netloc != self.headers.get("Host")):
                self.json_response(403, {"message": "不允许跨站保存"}); return
            if self.headers.get_content_type() != "application/json":
                self.json_response(415, {"message": "请使用 JSON 提交"}); return
        if path not in ("/api/state", "/api/auth/logout") and not self.client_allowed():
            self.json_response(429, {"status": "rate_limit", "message": "提交过于频繁，请稍后重试"}); return
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > 1024 * 1024 + 4096:
            self.json_response(413, {"status": "invalid_request", "message": "请求过大"}); return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict): raise ValueError("invalid payload")
        except Exception:
            self.json_response(400, {"status": "invalid_request", "message": "JSON 格式错误"}); return
        if path == '/api/auth/login':
            result=accounts.login(payload.get('username'),payload.get('password'))
            if not result:
                self.json_response(401,{'message':'账号或密码错误'}); return
            token,user=result
            self.send_response(200)
            self.send_header('Set-Cookie',f'mykb_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800')
            self.send_header('Content-Type','application/json; charset=utf-8')
            body=json.dumps({'user':user}).encode();self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body);return
        user=self.require_user()
        if not user:return
        if path == '/api/auth/logout':
            accounts.logout(self.headers.get('Cookie'))
            self.send_response(200);self.send_header('Set-Cookie','mykb_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'{}');return
        if path == '/api/auth/password':
            try:
                with accounts.connect() as conn:
                    row=conn.execute('SELECT password FROM users WHERE id=?',(user['id'],)).fetchone()
                    if not accounts.verify(payload.get('currentPassword',''),row['password']): raise ValueError('当前密码错误')
                    hashed=accounts.password_hash(payload.get('password'))
                    conn.execute('UPDATE users SET password=? WHERE id=?',(hashed,user['id']))
                    conn.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
                self.json_response(200,{'message':'密码已修改，请重新登录'})
            except ValueError as error:self.json_response(400,{'message':str(error)})
            return
        if path == '/api/state':
            try:
                accounts.write_state(user,payload.get('key'),payload.get('value'))
                self.json_response(200,{'ok':True})
            except ValueError as error:self.json_response(400,{'message':str(error)})
            return
        if path == '/api/admin/users':
            if not user['admin']:self.json_response(403,{'message':'仅管理员可管理用户'});return
            try:self.json_response(200,accounts.manage(payload,user))
            except ValueError as error:self.json_response(400,{'message':str(error)})
            return
        if path == '/api/index/rebuild' and not user['admin']:
            self.json_response(403,{'message':'仅管理员可重建索引'});return
        if path == '/api/articles':
            if not accounts.may(user,'create') or not accounts.visible(user,{'section':payload.get('section',''),'category':payload.get('category') or '综合'}):
                self.json_response(403,{'message':'没有此分类的新建权限'});return
        if path.startswith('/api/articles/') or path == '/api/judge':
            article_id=payload.get('problemId') if path=='/api/judge' else path.removeprefix('/api/articles/').removesuffix('/delete')
            if not self.allowed_article(user,article_id):self.json_response(403,{'message':'没有访问此文档的权限'});return
            action='delete' if path.endswith('/delete') else 'edit'
            if path!='/api/judge' and not accounts.may(user,action):self.json_response(403,{'message':'没有此文档的修改权限'});return
        if path == "/api/links/preview":
            try:
                self.json_response(200, fetch_link_metadata(payload.get("url")))
            except Exception as error:
                message = str(error) if isinstance(error, ValueError) else "读取网站失败，可手动填写后收藏"
                self.json_response(422, {"message": message})
            return
        if path == "/api/index/rebuild":
            status, result = rebuild_index()
            self.json_response(status, result); return
        if path == "/api/articles":
            status, result = create_article(payload)
            self.json_response(status, result); return
        if path == "/api/judge":
            status, result = run_judge(payload.get("problemId"), payload.get("source"))
            self.json_response(status, result); return
        if path.startswith("/api/articles/"):
            if path.endswith("/delete"):
                status, result = delete_article(path.removeprefix("/api/articles/").removesuffix("/delete"), payload.get("revision"), payload.get("copies"))
                self.json_response(status, result); return
            status, result = save_article(path.removeprefix("/api/articles/"), payload.get("body"), payload.get("revision"))
            self.json_response(status, result); return
        self.json_response(404, {"message": "Not found"})

    def do_GET(self):
        summary_index = parse_qs(urlsplit(self.path).query).get('view') == ['summary']
        path=self.request_path()
        self.path=path
        public=path in ('/api/config','/','/login','/index.html','/style.css','/favicon.svg','/logo.svg','/jkb-logo-v2.png','/interview','/problems','/learning','/papers','/notes','/saved') or path.startswith('/assets/')
        user=None
        if not public:
            user=self.require_user()
            if not user:return
        if path=='/api/config':self.json_response(200,{'siteName':SITE_NAME,'siteLogo':SITE_LOGO});return
        if path=='/api/auth/me':self.json_response(200,{'user':user});return
        if path=='/api/state':self.json_response(200,accounts.read_state(user));return
        if path=='/api/admin/users':
            if not user['admin']:self.json_response(403,{'message':'仅管理员可管理用户'});return
            data=json.loads(INDEX.read_text(encoding='utf-8'))
            catalog=sorted({(item['section'],item['category']) for item in data['items']})
            self.json_response(200,{'users':accounts.users(),'categories':[{'section':section,'category':category,'key':section+'::'+category} for section,category in catalog]});return
        if path=='/data/index.json':self.json_response(200,self.content_index(user,summary=summary_index));return
        if path.startswith('/data/articles/'):
            article_id=path.removeprefix('/data/articles/').removesuffix('.json')
            if not path.endswith('.json') or not self.allowed_article(user,article_id):self.json_response(403,{'message':'没有访问此文档的权限'});return
        elif path.startswith('/data/'):
            self.json_response(403,{'message':'不允许访问此文件'});return
        if path.startswith('/note-files/'):
            target=ROOT / path.lstrip('/')
            if not target.is_file():self.json_response(404,{'message':'附件不存在'});return
            data=json.loads(INDEX.read_text(encoding='utf-8'))
            notes=[item for item in data['items'] if item['section']=='notes']
            if any(not accounts.visible(user,item) for item in notes):
                permitted=False
                for item in notes:
                    if not accounts.visible(user,item):continue
                    article=ROOT / 'data' / 'articles' / (item['id']+'.json')
                    body=json.loads(article.read_text(encoding='utf-8'))['body']
                    references=re.findall(r'!\[[^\]]*\]\(([^)]+)\)|<img[^>]+src=["\']([^"\']+)',body)
                    for markdown_src,html_src in references:
                        src=(markdown_src or html_src).strip().strip('<>').split(' "')[0]
                        if urlsplit(src).scheme:continue
                        relative=src if src.startswith('assets/') else unquote(urlsplit(urljoin('/'+item['path'],src)).path).lstrip('/').removeprefix('notes/')
                        if '/note-files/'+relative==path:permitted=True;break
                    if permitted:break
                if not permitted:self.json_response(403,{'message':'没有访问此附件的权限'});return
        if not public and not (path.startswith('/api/') or path.startswith('/data/articles/') or path.startswith('/note-files/')):
            self.json_response(404,{'message':'Not found'});return
        if path.startswith("/api/articles/"):
            if not self.allowed_article(user,path.removeprefix('/api/articles/')):
                self.json_response(403,{'message':'没有访问此文档的权限'});return
            article_id = path.removeprefix("/api/articles/")
            with EDIT_LOCK:
                data = json.loads(INDEX.read_text(encoding="utf-8"))
                item = next((entry for entry in data["items"] if entry["id"] == article_id), None)
                if not item:
                    self.json_response(404, {"message": "文章不存在"}); return
                try:
                    source = source_path_for(item).read_bytes()
                    self.json_response(200, {"body": source.decode("utf-8"), "revision": hashlib.sha256(source).hexdigest(), "copies": sum(identity == article_id for identity in data["paths"].values())})
                except (ValueError, OSError) as error:
                    self.json_response(500, {"message": str(error)})
            return
        if path == "/api/health":
            self.json_response(200,{"ok":True,"judge":"ready" if VENV.exists() else "missing","supported":len(TESTS)}); return
        if path in ["/","/login","/interview","/problems","/learning","/papers","/notes","/saved"]:
            self.path="/index.html"
        if self.command=='HEAD':super().do_HEAD()
        else:super().do_GET()

    def send_head(self):
        # Public text assets are precompressed by the build; the browser can
        # revalidate and reuse them without downloading the body again.
        target = Path(self.translate_path(self.path))
        compressed = Path(str(target) + '.gz')
        if (target.suffix not in ('.js', '.css', '.html') or
                not accepts_gzip(self.headers.get('Accept-Encoding')) or
                not target.is_file() or not compressed.is_file() or
                compressed.stat().st_mtime_ns < target.stat().st_mtime_ns):
            return super().send_head()
        stat = compressed.stat()
        etag = '"' + str(stat.st_mtime_ns) + '-' + str(stat.st_size) + '-gzip"'
        if etag in [tag.strip() for tag in self.headers.get('If-None-Match', '').split(',')]:
            self.send_response(304)
            self.send_header('ETag', etag)
            self.send_header('Vary', 'Accept-Encoding')
            self.end_headers()
            return None
        handle = compressed.open('rb')
        self.send_response(200)
        self.send_header('Content-Type', self.guess_type(str(target)))
        self.send_header('Content-Encoding', 'gzip')
        self.send_header('Vary', 'Accept-Encoding')
        self.send_header('ETag', etag)
        self.send_header('Last-Modified', self.date_time_string(stat.st_mtime))
        self.send_header('Content-Length', str(stat.st_size))
        self.end_headers()
        return handle

    def do_HEAD(self):
        self.do_GET()

    def end_headers(self):
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Cache-Control","no-store" if self.request_path().startswith(("/api/", "/data/", "/note-files/")) else "no-cache")
        super().end_headers()

if __name__ == "__main__":
    accounts.initialize()
    parser=argparse.ArgumentParser()
    parser.add_argument("--host",default=HOST)
    parser.add_argument("--port",type=int,default=PORT)
    args=parser.parse_args()
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    print(f"MyKB: http://{args.host}:{args.port} · {len(TESTS)} judgeable problems",flush=True)
    server.serve_forever()
