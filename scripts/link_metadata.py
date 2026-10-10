"""Bounded public-web link previews; connections pin validated DNS addresses."""
import http.client
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
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title': self.in_title = True
        if tag == 'meta':
            key = (attrs.get('property') or attrs.get('name') or '').lower()
            self.meta.setdefault(key, attrs.get('content', ''))
        if tag == 'link' and 'icon' in attrs.get('rel', '').lower().split():
            self.icon = self.icon or attrs.get('href', '')
    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
    def handle_data(self, text):
        if self.in_title: self.title.append(text)


def fetch_link_metadata(url):
    for _ in range(6):
        parsed, address, port = public_url(url)
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; JKBBookmark/1.0)', 'Accept': 'text/html,application/xhtml+xml', 'Accept-Encoding': 'identity'}
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
            if not any(kind in response_headers.get('Content-Type', '').lower() for kind in ('text/html', 'application/xhtml+xml')):
                raise ValueError('此链接没有网页预览，可直接收藏')
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024: raise ValueError('网页过大，可手动填写后收藏')
            charset = re.search(r'charset=["\']?([\w-]+)', response_headers.get('Content-Type', ''), re.I)
            if not charset: charset = re.search(r'charset=["\']?([\w-]+)', data[:8192].decode('ascii', 'ignore'), re.I)
            try: html = data.decode(charset.group(1) if charset else 'utf-8', 'replace')
            except LookupError: html = data.decode('utf-8', 'replace')
        finally:
            if response: response.close()
            if connection: connection.close()
        parser = PreviewParser(); parser.feed(html)
        def clean(value, length): return re.sub(r'\s+', ' ', value).strip()[:length]
        def asset(value):
            target = urljoin(url, value) if value else ''
            parts = urlsplit(target)
            return target if parts.scheme in ('http', 'https') and parts.hostname and not parts.username and not parts.password else ''
        meta = parser.meta
        return {'title': clean(meta.get('og:title') or meta.get('twitter:title') or ''.join(parser.title) or parsed.hostname, 180), 'description': clean(meta.get('og:description') or meta.get('description') or meta.get('twitter:description') or '', 500), 'image': asset(meta.get('og:image') or meta.get('twitter:image') or meta.get('twitter:image:src')), 'favicon': asset(parser.icon)}
    raise ValueError('网站跳转过多，可手动填写后收藏')
