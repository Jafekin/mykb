"""Extract display titles without treating code comments as headings."""
import re
import html


def article_excerpt(body, limit=180, prefer_summary=False):
    """Take the first prose paragraph, excluding headings and document metadata."""
    lines = body.lstrip('\ufeff').splitlines()
    if prefer_summary:
        summary = re.search(r'^#{1,6}\s+一句话摘要\s*\n(.*?)(?=^#{1,6}\s|\Z)', body, re.M | re.S)
        if summary:
            excerpt = article_excerpt(summary.group(1), limit)
            if excerpt:
                return excerpt

    if lines and lines[0].strip() == '---':
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
        if end is not None:
            lines = lines[end + 1:]
    # Problem statements are more useful than boilerplate above them.
    start = next((i for i, line in enumerate(lines) if re.match(
        r'^#{1,6}\s+(?:题目描述|题目介绍|问题描述|题目说明|Problem Description)\s*$', line, re.I)), None)
    if start is not None:
        lines = lines[start + 1:]
    paragraph = []
    fence = None
    for line in lines:
        stripped = line.strip()
        marker = re.match(r'^(`{3,}|~{3,})', stripped)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
            continue
        if marker:
            if paragraph: break
            fence = marker[1]
            continue
        plain = re.sub(r'^[>\s-]+', '', stripped).replace('**', '')
        if re.match(r'^(?:难度|(?:技术)?分类|标签|原题|时间限制|内存限制|发布日期|发布时间|作者|论文分类|来源|题目链接)\s*[：:]', plain):
            continue
        if not stripped or re.match(r'^(?:#{1,6}\s|\||[-*_]{3,}\s*$)', stripped):
            if paragraph: break
            continue
        text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', stripped)
        text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
        text = re.sub(r'https?://\S+|<[^>]+>', '', text)
        text = re.sub(r'^[>\s]+|[*`]', '', text).strip()
        if text:
            paragraph.append(text)
    return html.unescape(' '.join(paragraph))[:limit]


def article_title(body, fallback):
    lines = body.lstrip('\ufeff').splitlines()
    metadata_title = None
    if lines and lines[0].strip() == '---':
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
        if end is not None:
            for line in lines[1:end]:
                match = re.match(r'^title:[ \t]*(.+?)\s*$', line)
                if match:
                    metadata_title = match.group(1).strip().strip('\"\'')
            lines = lines[end + 1:]
    headings = []
    fence = None
    for line in lines:
        if fence:
            if re.match(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(fence[1]) + r',}[ \t]*$', line):
                fence = None
            continue
        opening = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if opening:
            marker, info = opening.groups()
            if marker[0] != '`' or '`' not in info:
                fence = (marker[0], len(marker))
                continue
        heading = re.match(r'^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$', line)
        if heading:
            text = re.sub(r'[ \t]+#+[ \t]*$', '', heading.group(2))
            # Titles are plain text; inline code markers are presentation only.
            text = re.sub(r'`+([^`]+)`+', r'\1', text)
            headings.append((len(heading.group(1)), text))
    return next((text for level, text in headings if level == 1), None) or metadata_title or next((text for _, text in headings), None) or fallback
