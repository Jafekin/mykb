"""Bounded public-web link previews; connections pin validated DNS addresses."""
import http.client
import json
import zlib
from html import unescape
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin
from urllib.request import build_opener, HTTPRedirectHandler, Request, getproxies
from urllib.error import HTTPError


def public_url(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('请输入有效的网址')
    parsed = urlsplit(url.strip())
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('网址仅支持公开的 http 或 https 链接')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('仅支持公开网站，不能读取内网地址')
    return parsed, addresses[0][4][0], port


class PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}; self.title = []; self.in_title = False; self.icon = ''
        self.heading = []; self.paragraphs = []; self.scripts = []
        self.capture = None; self.script = None; self.hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title': self.in_title = True
        if tag == 'meta':
            key = (attrs.get('property') or attrs.get('name') or attrs.get('itemprop') or '').lower()
            value = attrs.get('content', '').strip()
            if value and not self.meta.get(key): self.meta[key] = value
        if tag == 'link' and any('icon' in rel for rel in attrs.get('rel', '').lower().split()):
            self.icon = self.icon or attrs.get('href', '')
        if tag == 'script': self.script = [attrs.get('type', '').lower(), []]
        if tag in ('style', 'noscript'): self.hidden += 1
        if tag in ('h1', 'p') and not self.script and not self.hidden:
            self.capture = [tag, []]

    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
        if tag == 'script' and self.script:
            self.scripts.append((self.script[0], ''.join(self.script[1])))
            self.script = None
        if tag in ('style', 'noscript'): self.hidden = max(0, self.hidden - 1)
        if self.capture and tag == self.capture[0]:
            value = ''.join(self.capture[1]).strip()
            if value: (self.heading if tag == 'h1' else self.paragraphs).append(value)
            self.capture = None

    def handle_data(self, text):
        if self.in_title: self.title.append(text)
        if self.script: self.script[1].append(text)
        elif self.capture and not self.hidden: self.capture[1].append(text)


def parse_metadata(html, url):
    parser = PreviewParser(); parser.feed(html)
    meta = parser.meta
    structured = {}
    def visit(value, depth=0):
        if depth > 20: return
        if isinstance(value, list):
            for item in value: visit(item, depth + 1)
        elif isinstance(value, dict):
            kinds = value.get('@type', [])
            if isinstance(kinds, str): kinds = [kinds]
            if any(kind in ('Article', 'NewsArticle', 'BlogPosting', 'TechArticle', 'ScholarlyArticle', 'VideoObject', 'WebPage', 'Product') for kind in kinds):
                for key in ('headline', 'name', 'description', 'image', 'thumbnailUrl'):
                    if value.get(key) and key not in structured: structured[key] = value[key]
            for item in value.values():
                if isinstance(item, (dict, list)): visit(item, depth + 1)
    for kind, script in parser.scripts:
        if kind == 'application/ld+json':
            try: visit(json.loads(script))
            except (ValueError, RecursionError): pass
    # Opus embeds server-rendered article data even when cover meta tags are absent.
    if bilibili_article_url(url):
        for _, script in parser.scripts:
            match = re.search(r'\b(?:window\.)?__INITIAL_STATE__\s*=\s*', script)
            if not match: continue
            try:
                state, _ = json.JSONDecoder().raw_decode(script[match.end():])
                detail = state.get('detail', {})
                modules = detail.get('modules', [])
                for module in modules:
                    title = (module.get('module_title') or {}).get('text')
                    if title: structured['headline'] = title
                    top = (module.get('module_top') or {}).get('display') or {}
                    pics = (top.get('album') or {}).get('pics') or []
                    if pics and isinstance(pics[0], dict): structured['image'] = pics[0].get('url')
                    paragraphs = (module.get('module_content') or {}).get('paragraphs') or []
                    for paragraph in paragraphs:
                        nodes = (paragraph.get('text') or {}).get('nodes') or []
                        text = ''.join((node.get('word') or {}).get('words', '') for node in nodes).strip()
                        if text and not structured.get('description'): structured['description'] = text
                if structured.get('headline'): meta['og:title'] = structured['headline']
            except (ValueError, TypeError, AttributeError, RecursionError):
                continue
    # WeChat exposes article metadata as JS strings even when standard tags are absent.
    wechat = {}
    if urlsplit(url).hostname == 'mp.weixin.qq.com':
        for key, variable in [('title', 'msg_title'), ('description', 'msg_desc'), ('image', 'msg_cdn_url')]:
            match = re.search(r"\b" + variable + r"\s*=\s*([\"'])(.*?)\1", html, re.S)
            if match: wechat[key] = unescape(match.group(2).replace(r'\/', '/'))
    def clean(value, length):
        return re.sub(r'\s+', ' ', unescape(value)).strip()[:length] if isinstance(value, str) else ''
    def asset(value):
        if isinstance(value, list): value = next(iter(value), '')
        if isinstance(value, dict): value = value.get('url') or value.get('contentUrl') or ''
        if not isinstance(value, str): return ''
        target = urljoin(url, unescape(value.strip())) if value.strip() else ''
        try:
            parts = urlsplit(target)
            if parts.scheme == 'http' and (parts.hostname == 'hdslb.com' or (parts.hostname or '').endswith('.hdslb.com')):
                target = 'https:' + target[len('http:'):]
            return target if parts.scheme in ('http', 'https') and parts.hostname and not parts.username and not parts.password else ''
        except ValueError: return ''
    title = next((clean(v, 180) for v in (meta.get('og:title'), meta.get('twitter:title'), wechat.get('title'), structured.get('headline'), structured.get('name'), meta.get('title'), ''.join(parser.title), next(iter(parser.heading), ''), urlsplit(url).hostname) if clean(v, 180)), '')
    description = next((clean(v, 500) for v in (meta.get('og:description'), meta.get('description'), meta.get('twitter:description'), wechat.get('description'), structured.get('description'), next((p for p in parser.paragraphs if len(p) >= 40), '')) if clean(v, 500)), '')
    image = next((asset(v) for v in (meta.get('og:image:secure_url'), meta.get('og:image'), meta.get('twitter:image'), meta.get('twitter:image:src'), meta.get('image'), wechat.get('image'), structured.get('image'), structured.get('thumbnailUrl')) if asset(v)), '')
    return {'title': title, 'description': description, 'image': image, 'favicon': asset(parser.icon) or urljoin(url, '/favicon.ico')}


def bilibili_article_url(url):
    parsed = urlsplit(url)
    return parsed.hostname in ('www.bilibili.com', 'bilibili.com', 'm.bilibili.com') and bool(
        re.fullmatch(r'/(?:opus/[0-9]+|read/cv[0-9]+)/?', parsed.path))


def bilibili_video_query(url):
    parsed = urlsplit(url)
    if parsed.hostname not in ('www.bilibili.com', 'bilibili.com', 'm.bilibili.com'):
        return None
    match = re.fullmatch(r'/video/(BV[0-9A-Za-z]{10}|av[0-9]+)/?', parsed.path)
    if not match: return None
    identifier = match.group(1)
    return ('bvid=' + identifier) if identifier.startswith('BV') else ('aid=' + identifier[2:])


def fetch_link_metadata(url):
    # Use video data rather than Bilibili's HTTP-200 error-page templates.
    public_url(url)
    query = bilibili_video_query(url)
    if query:
        try:
            payload = fetch_document('https://api.bilibili.com/x/web-interface/view?' + query, json_response=True)
            video = payload.get('data')
            if payload.get('code') == 0 and isinstance(video, dict) and isinstance(video.get('title'), str) and video['title'].strip():
                return parse_metadata('<script type="application/ld+json">' + json.dumps({
                    '@type': 'VideoObject', 'name': video['title'],
                    'description': video.get('desc', ''), 'thumbnailUrl': video.get('pic', '')
                }, ensure_ascii=True).replace('<', r'\u003c') + '</script>', url)
        except (ValueError, OSError, http.client.HTTPException):
            pass
    return fetch_document(url)


def fetch_document(url, json_response=False):
    for _ in range(6):
        parsed, address, port = public_url(url)
        headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', 'Accept': 'text/html,application/xhtml+xml', 'Accept-Encoding': 'gzip, deflate', 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'}
        # CSDN rejects article requests without its site referer (HTTP 521).
        # Recompute on every redirect so this header is never sent to other hosts.
        if parsed.hostname in ('api.bilibili.com', 'www.bilibili.com', 'bilibili.com', 'm.bilibili.com'):
            headers['Referer'] = 'https://www.bilibili.com/'
        if parsed.hostname in ('blog.csdn.net', 'm.blog.csdn.net'):
            headers['Referer'] = 'https://blog.csdn.net/'
        connection = None
        response = None
        try:
            if getproxies().get(parsed.scheme):
                class NoRedirect(HTTPRedirectHandler):
                    def redirect_request(self, *args): return None
                try:
                    response = build_opener(NoRedirect).open(Request(url, headers=headers), timeout=10)
                except HTTPError as error:
                    response = error
                status = response.code
                response_headers = response.headers
            else:
                connection = http.client.HTTPConnection(parsed.hostname, port, timeout=10)
                sock = socket.create_connection((address, port), timeout=10)
                if parsed.scheme == 'https':
                    try: sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
                    except Exception:
                        sock.close(); raise
                connection.sock = sock
                headers['Host'] = parsed.netloc
                connection.request('GET', (parsed.path or '/') + ('?' + parsed.query if parsed.query else ''), headers=headers)
                response = connection.getresponse()
                status = response.status
                response_headers = response.headers
            if status in (301, 302, 303, 307, 308):
                location = response_headers.get('Location')
                if not location: raise ValueError('网站跳转地址无效')
                url = urljoin(url, location); continue
            if status != 200: raise ValueError('网站暂时无法读取，可手动填写后收藏')
            if not any(kind in response_headers.get('Content-Type', '').lower() for kind in (('application/json',) if json_response else ('text/html', 'application/xhtml+xml'))):
                raise ValueError('此链接没有网页预览，可直接收藏')
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024: raise ValueError('网页过大，可手动填写后收藏')
            encoding = response_headers.get('Content-Encoding', '').lower()
            if encoding in ('gzip', 'deflate'):
                decoder = zlib.decompressobj(31 if encoding == 'gzip' else zlib.MAX_WBITS)
                data = decoder.decompress(data, 2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024 or decoder.unconsumed_tail:
                    raise ValueError('网页过大，可手动填写后收藏')
            charset = re.search(r'charset=["\']?([\w-]+)', response_headers.get('Content-Type', ''), re.I)
            if not charset: charset = re.search(r'charset=["\']?([\w-]+)', data[:8192].decode('ascii', 'ignore'), re.I)
            try: html = data.decode(charset.group(1) if charset else 'utf-8', 'replace')
            except LookupError: html = data.decode('utf-8', 'replace')
        finally:
            if response: response.close()
            if connection: connection.close()
        if json_response:
            payload = json.loads(html)
            if not isinstance(payload, dict): raise ValueError('视频信息格式无效')
            return payload
        result = parse_metadata(html, url)
        if (bilibili_video_query(url) or bilibili_article_url(url)) and (
            re.search(r'视频去哪[了儿]|视频不见了|视频不存在|视频已被删除|视频已下架|页面不存在|页面不见了|出错了', result['title'])
            or re.search(r'\{\$\d+\}|\bundefined\b', result['description'])
        ):
            raise ValueError('B站未返回有效' + ('图文' if bilibili_article_url(url) else '视频') + '信息，可能需要登录或内容暂不可用，可手动填写后收藏')
        return result
    raise ValueError('网站跳转过多，可手动填写后收藏')
