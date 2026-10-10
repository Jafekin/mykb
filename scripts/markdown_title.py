"""Extract display titles without treating code comments as headings."""
import re


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
