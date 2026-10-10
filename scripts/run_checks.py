"""Run the application checks in a fresh disposable project, never on live data."""
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='mykb-checks-') as temporary:
    root = Path(temporary)
    for name in ('src','scripts','examples'):
        shutil.copytree(PROJECT/name,root/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','jkb-logo-v2.png','jkb-logo-v2-prompt.txt'))
    (root/'node_modules').symlink_to(PROJECT/'node_modules',target_is_directory=True)
    shutil.copyfile(PROJECT/'package.json',root/'package.json')
    env=dict(os.environ)
    for key in ('MYKB_CONTENT_ROOT','MYKB_NOTES_ROOT','LLMFORGE_CONTENT','JAFEKIN_NOTES'):
        env.pop(key,None)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env['SITE_URL']=f'http://127.0.0.1:{port}'
    def run(*args):subprocess.run(args,cwd=root,env=env,check=True)
    run('python3','scripts/check_markdown_title.py')
    run('python3','scripts/check_link_metadata.py')
    run('python3','scripts/check_content_cache.py')
    run('python3','scripts/check_auto_sync.py')
    run('python3','scripts/setup.py')
    for relative, title in (
        ('传统算法/基础算法.md', '传统基础算法'),
        ('传统算法/滑动窗口/窗口.md', '传统滑动窗口'),
        ('传统算法/图搜索/搜索.md', '传统图搜索'),
        ('滑动窗口/知识点窗口.md', '知识点滑动窗口'),
    ):
        fixture = root/'knowledge-base'/'手撕题'/relative
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text('# '+title+'\n\n分类回归测试正文。\n')
    note_fixture = next((root/'knowledge-base/note').rglob('*.md'))
    with note_fixture.open('a') as handle:
        handle.write('\n' + '加载测试正文。' * 60 + '\n\n仅正文搜索标记XYZ。\n')
    run('python3','scripts/import_content.py')
    run('node','scripts/build.mjs')
    with (root/'server.log').open('w+') as log:
        server=subprocess.Popen(['python3','scripts/serve.py','--host','127.0.0.1','--port',str(port)],cwd=root,env=env,stdout=log,stderr=log)
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(100):
                try:
                    with opener.open(env['SITE_URL']+'/api/config',timeout=1):break
                except OSError:
                    if server.poll() is not None:
                        log.seek(0);raise RuntimeError(log.read())
                    time.sleep(.1)
            else:raise RuntimeError('Test server did not start')
            run('python3','scripts/check_accounts.py')
            run('node','scripts/check_accounts_ui.cjs')
            run('node','scripts/check_problem_categories.cjs')
            run('node','scripts/check_loading_ui.cjs')
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()
    print('MyKB checks passed in an isolated example knowledge base.')
