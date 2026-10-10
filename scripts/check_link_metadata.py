"""Deterministic previews for common publishing formats, without external services."""
import gzip
import io
import unittest
from unittest.mock import patch
from link_metadata import parse_metadata, fetch_link_metadata, public_url


class MetadataTests(unittest.TestCase):
    def test_standard_publishers(self):
        for host in ('github.com', 'zhihu.com', 'juejin.cn', 'blog.csdn.net', 'bilibili.com', 'youtube.com', 'medium.com', 'arxiv.org'):
            with self.subTest(host=host):
                result = parse_metadata('<meta property="og:title" content=""><meta property="og:title" content="文章 &amp; 视频"><meta name="description" content="简介"><meta property="og:image" content="/cover.jpg"><link rel="apple-touch-icon" href="/icon.png">', 'https://' + host + '/article')
                self.assertEqual(result['title'], '文章 & 视频')
                self.assertEqual(result['image'], 'https://' + host + '/cover.jpg')
                self.assertEqual(result['favicon'], 'https://' + host + '/icon.png')

    def test_structured_data(self):
        result = parse_metadata('<script type="application/ld+json">{"@graph":[{"@type":"BlogPosting","headline":"技术文章","description":"结构化摘要","image":[{"url":"//cdn.example.com/a.jpg"}]}]}</script>', 'https://example.com/post')
        self.assertEqual(result['title'], '技术文章')
        self.assertEqual(result['description'], '结构化摘要')
        self.assertEqual(result['image'], 'https://cdn.example.com/a.jpg')

    def test_wechat(self):
        result = parse_metadata('var msg_title = "微信文章 &amp; 笔记"; var msg_desc = "文章简介"; var msg_cdn_url = "https://example.com/a.jpg";', 'https://mp.weixin.qq.com/s/abc')
        self.assertEqual(result['title'], '微信文章 & 笔记')
        self.assertEqual(result['description'], '文章简介')
        self.assertTrue(result['image'].endswith('/a.jpg'))

    def test_fallback_and_unsafe_images(self):
        result = parse_metadata('<script>hidden</script><h1>正文标题</h1><p>' + '正文摘要' * 20 + '</p><meta property="og:image" content="javascript:alert(1)"><meta name="twitter:image" content="/safe.jpg">', 'https://example.com/a')
        self.assertEqual(result['title'], '正文标题')
        self.assertEqual(result['description'], '正文摘要' * 20)
        self.assertEqual(result['image'], 'https://example.com/safe.jpg')

    def test_malformed_json(self):
        self.assertEqual(parse_metadata('<script type="application/ld+json">{broken</script><title>正常标题</title>', 'https://example.com')['title'], '正常标题')

    def test_gzip_and_chinese_charset(self):
        response = io.BytesIO(gzip.compress('<title>中文标题</title>'.encode('gb18030')))
        response.code = 200
        response.headers = {'Content-Type': 'text/html; charset=gb18030', 'Content-Encoding': 'gzip'}
        with patch('link_metadata.public_url', return_value=(__import__('urllib.parse', fromlist=['urlsplit']).urlsplit('https://example.com'), '93.184.216.34', 443)), patch('link_metadata.getproxies', return_value={'https': 'http://proxy'}), patch('link_metadata.build_opener') as opener:
            opener.return_value.open.return_value = response
            self.assertEqual(fetch_link_metadata('https://example.com')['title'], '中文标题')

    def test_bilibili_video_api(self):
        url = 'https://www.bilibili.com/video/BV1twPFejEwn/?vd_source=tracking&spm_id_from=333.788'
        payload = {'code': 0, 'data': {'title': '视频标题', 'desc': '真实简介', 'pic': '//i0.hdslb.com/cover.jpg'}}
        with patch('link_metadata.public_url'), patch('link_metadata.fetch_document', return_value=payload) as fetch:
            result = fetch_link_metadata(url)
        self.assertEqual(result['title'], '视频标题')
        self.assertEqual(result['description'], '真实简介')
        self.assertEqual(result['image'], 'https://i0.hdslb.com/cover.jpg')
        self.assertEqual(fetch.call_args.args[0], 'https://api.bilibili.com/x/web-interface/view?bvid=BV1twPFejEwn')

    def test_bilibili_error_page_rejected(self):
        response = io.BytesIO('<title>视频去哪了呢？_哔哩哔哩_bilibili</title><meta name="description" content="{$0}, 视频播放量 undefined">'.encode())
        response.code = 200
        response.headers = {'Content-Type': 'text/html'}
        with patch('link_metadata.public_url', return_value=(__import__('urllib.parse', fromlist=['urlsplit']).urlsplit('https://www.bilibili.com/video/BV1twPFejEwn/'), '93.184.216.34', 443)), patch('link_metadata.getproxies', return_value={'https': 'http://proxy'}), patch('link_metadata.build_opener') as opener:
            opener.return_value.open.return_value = response
            from link_metadata import fetch_document
            with self.assertRaisesRegex(ValueError, 'B站未返回有效视频信息'):
                fetch_document('https://www.bilibili.com/video/BV1twPFejEwn/')

    def test_bilibili_opus_embedded_article(self):
        import json
        state = {'detail': {'modules': [
            {'module_title': {'text': '图文标题'}},
            {'module_top': {'display': {'album': {'pics': [{'url': 'http://i0.hdslb.com/article.png'}]}}}},
            {'module_content': {'paragraphs': [{'text': {'nodes': [{'word': {'words': '文章简介'}}]}}]}}
        ]}}
        html = '<title>图文标题 - 哔哩哔哩</title><script>window.__INITIAL_STATE__=' + json.dumps(state) + ';window.other=1;</script>'
        result = parse_metadata(html, 'https://www.bilibili.com/opus/1257024987855847425?from=search')
        self.assertEqual(result['title'], '图文标题')
        self.assertEqual(result['description'], '文章简介')
        self.assertEqual(result['image'], 'https://i0.hdslb.com/article.png')
        result = parse_metadata('<script>window.__INITIAL_STATE__={bad;</script><title>文章</title>', 'https://www.bilibili.com/opus/123')
        self.assertEqual(result['title'], '文章')

    def test_private_addresses_rejected(self):
        with patch('link_metadata.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]):
            with self.assertRaises(ValueError): public_url('http://example.com')

    def test_csdn_request_and_redirect_headers(self):
        from urllib.parse import urlsplit
        article = 'https://blog.csdn.net/csdnnews/article/details/167391834?spm=1000.2115.3001.10524'
        redirect = io.BytesIO(b'')
        redirect.code = 302
        redirect.headers = {'Location': 'https://example.com/article'}
        page = io.BytesIO('<title>文章标题</title>'.encode())
        page.code = 200
        page.headers = {'Content-Type': 'text/html'}
        def validate(url): return urlsplit(url), '93.184.216.34', 443
        with patch('link_metadata.public_url', side_effect=validate), patch('link_metadata.getproxies', return_value={'https': 'http://proxy'}), patch('link_metadata.build_opener') as opener:
            opener.return_value.open.side_effect = [redirect, page]
            self.assertEqual(fetch_link_metadata(article)['title'], '文章标题')
            first, second = [call.args[0] for call in opener.return_value.open.call_args_list]
            self.assertEqual(first.full_url, article)
            self.assertEqual(first.get_header('Referer'), 'https://blog.csdn.net/')
            self.assertIn('AppleWebKit', first.get_header('User-agent'))
            self.assertIsNone(second.get_header('Referer'))


if __name__ == '__main__': unittest.main()
