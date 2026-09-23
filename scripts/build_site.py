#!/usr/bin/env python3
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
]

HEADING_RE = re.compile(r'^\s*(\d+(?:\.\d+)*\.)\s*(.+?)\s*$')


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def credentials_from_env():
    raw = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '').strip()
    if not raw:
        raise RuntimeError('GOOGLE_SERVICE_ACCOUNT_JSON secret is missing.')
    info = json.loads(raw)
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def fetch_document(doc_id, creds):
    docs = build('docs', 'v1', credentials=creds, cache_discovery=False)
    try:
        doc = docs.documents().get(documentId=doc_id, includeTabsContent=True).execute()
    except TypeError:
        doc = docs.documents().get(documentId=doc_id).execute()
    drive = build('drive', 'v3', credentials=creds, cache_discovery=False)
    meta = drive.files().get(fileId=doc_id, fields='id,name,modifiedTime,webViewLink').execute()
    return doc, meta


def first_document_tab(doc):
    """Return body/inlineObjects/lists from the first document tab, or legacy root."""
    if doc.get('tabs'):
        stack = list(doc['tabs'])
        while stack:
            tab = stack.pop(0)
            dt = tab.get('documentTab')
            if dt and dt.get('body'):
                return {
                    'body': dt.get('body', {}),
                    'inlineObjects': dt.get('inlineObjects', {}),
                    'lists': dt.get('lists', {}),
                    'tabProperties': tab.get('tabProperties', {}),
                }
            stack[0:0] = tab.get('childTabs', [])
    return {
        'body': doc.get('body', {}),
        'inlineObjects': doc.get('inlineObjects', {}),
        'lists': doc.get('lists', {}),
        'tabProperties': {},
    }


def rgb_to_hex(rgb):
    if not rgb:
        return None
    vals = []
    for k in ('red', 'green', 'blue'):
        v = rgb.get(k, 0)
        vals.append(max(0, min(255, round(v * 255))))
    return '#%02x%02x%02x' % tuple(vals)


def color_from_style(style, key):
    obj = style.get(key) or {}
    color = obj.get('color', {}).get('rgbColor')
    return rgb_to_hex(color)


def safe_slug(text):
    text = re.sub(r'^\s*\d+(?:\.\d+)*\.\s*', '', text).strip()
    text = re.sub(r'[^0-9A-Za-z가-힣]+', '-', text).strip('-').lower()
    return text or 'section'


def heading_depth(text):
    m = HEADING_RE.match(text.strip())
    if not m:
        return None
    num = m.group(1)
    return num.count('.') + 1  # 1. -> 2, 1.1. -> 3 (matches existing CSS hierarchy)


def heading_number_and_title(text):
    m = HEADING_RE.match(text.strip())
    if not m:
        return '', text.strip()
    return m.group(1), m.group(2).strip()


def named_heading_depth(paragraph):
    named = (paragraph.get('paragraphStyle') or {}).get('namedStyleType', '')
    if named.startswith('HEADING_'):
        try:
            n = int(named.split('_')[-1])
            return min(6, n + 1)
        except ValueError:
            pass
    return None


def paragraph_plain_text(paragraph):
    out = []
    for el in paragraph.get('elements', []):
        if 'textRun' in el:
            out.append(el['textRun'].get('content', ''))
    return ''.join(out).rstrip('\n')


def structural_plain_text(struct):
    if 'paragraph' in struct:
        return paragraph_plain_text(struct['paragraph'])
    if 'table' in struct:
        bits = []
        for row in struct['table'].get('tableRows', []):
            for cell in row.get('tableCells', []):
                for child in cell.get('content', []):
                    bits.append(structural_plain_text(child))
        return ' '.join(x for x in bits if x)
    return ''


def is_private_heading(text, rules):
    return any(re.search(p, text, re.I) for p in rules.get('private_section_title_patterns', []))



def extract_infobox_table(table):
    """Extract the actual team infobox from the source's combined TOC+infobox table.

    The master Google Doc stores the visual TOC on the left and the team
    information box on the right inside one 4-column table. Rendering that
    whole table as an infobox turns the TOC into navy header cells. Detect the
    label column (팀명/업종명/설립일/...) and project only that column plus the
    value column immediately to its right.
    """
    rows = table.get('tableRows', [])
    if not rows:
        return None

    labels = {
        '팀명', '업종명', '설립일', '팀장', '관리자', '부장',
        '슬로건', '최우선가치', '상징색', '플랫폼', '팀원 전용'
    }
    scores = {}
    max_cols = 0
    for row in rows:
        cells = row.get('tableCells', [])
        max_cols = max(max_cols, len(cells))
        for ci, cell in enumerate(cells):
            txt = normalized_space(' '.join(structural_plain_text(c) for c in cell.get('content', [])))
            if txt in labels:
                scores[ci] = scores.get(ci, 0) + 1

    if not scores:
        return None
    label_col = max(scores, key=scores.get)
    value_col = label_col + 1
    if value_col >= max_cols:
        return None

    projected_rows = []
    for row in rows:
        cells = row.get('tableCells', [])
        picked = []
        for ci in (label_col, value_col):
            if ci < len(cells):
                picked.append(cells[ci])
        if picked:
            new_row = dict(row)
            new_row['tableCells'] = picked
            projected_rows.append(new_row)

    if not projected_rows:
        return None
    out = dict(table)
    out['tableRows'] = projected_rows
    out['columns'] = 2
    return out

def should_strip_link(url, rules):
    if not url:
        return False
    for p in rules.get('keep_link_url_patterns', []):
        if re.search(p, url, re.I):
            return False
    try:
        host = (urlparse(url).hostname or '').lower()
    except Exception:
        host = ''
    for p in rules.get('strip_link_host_patterns', []):
        if re.search(p, host, re.I):
            return True
    return False


def image_ext(content_type, uri):
    mapping = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif', 'image/webp': '.webp'}
    if content_type in mapping:
        return mapping[content_type]
    path = urlparse(uri).path.lower()
    for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
        if path.endswith(ext):
            return '.jpg' if ext == '.jpeg' else ext
    return '.png'


def dimension_to_px(dim):
    """Convert a Google Docs Dimension to CSS pixels.

    Docs inline-object sizes are normally reported in points. Preserving the
    display size is important for tiny link/platform icons: without it the
    browser renders the source bitmap at its intrinsic size.
    """
    if not dim or dim.get('magnitude') is None:
        return None
    try:
        value = float(dim.get('magnitude'))
    except (TypeError, ValueError):
        return None
    unit = str(dim.get('unit') or 'PT').upper()
    if unit == 'PT':
        value *= 96.0 / 72.0
    # Defensive support in case an alternate unit is ever returned.
    elif unit == 'IN':
        value *= 96.0
    elif unit == 'CM':
        value *= 96.0 / 2.54
    return max(1, round(value, 2))


def normalized_space(text):
    return re.sub(r'\s+', ' ', text or '').strip()


class Renderer:
    def __init__(self, context, out_dir, creds, rules):
        self.inline_objects = context.get('inlineObjects', {})
        self.out_dir = Path(out_dir)
        self.img_dir = self.out_dir / 'assets' / 'generated'
        self.img_dir.mkdir(parents=True, exist_ok=True)
        self.session = AuthorizedSession(creds)
        self.rules = rules
        self.image_cache = {}
        self.headings = []
        self.heading_ids = {}
        self.seen_slugs = {}

    def unique_anchor(self, number, title):
        base = f"{number.rstrip('.').replace('.', '-')}-{safe_slug(title)}" if number else safe_slug(title)
        n = self.seen_slugs.get(base, 0)
        self.seen_slugs[base] = n + 1
        return base if n == 0 else f'{base}-{n+1}'

    def download_inline_image(self, object_id):
        if object_id in self.image_cache:
            return self.image_cache[object_id]
        obj = self.inline_objects.get(object_id, {})
        emb = (obj.get('inlineObjectProperties') or {}).get('embeddedObject', {})
        props = emb.get('imageProperties', {})
        uri = props.get('contentUri')
        if not uri:
            return None
        r = self.session.get(uri, timeout=45)
        if r.status_code >= 400:
            r = requests.get(uri, timeout=45)
            r.raise_for_status()
        ctype = r.headers.get('content-type', '').split(';')[0].lower()
        ext = image_ext(ctype, uri)
        digest = hashlib.sha1((object_id + uri).encode('utf-8')).hexdigest()[:14]
        name = f'doc-{digest}{ext}'
        path = self.img_dir / name
        path.write_bytes(r.content)
        rel = f'assets/generated/{name}'
        self.image_cache[object_id] = rel
        return rel

    def render_inline(self, element):
        if 'textRun' in element:
            tr = element['textRun']
            text = tr.get('content', '').replace('\n', '')
            if not text:
                return ''
            style = tr.get('textStyle') or {}
            inner = html.escape(text)
            if style.get('bold'):
                inner = f'<strong>{inner}</strong>'
            if style.get('italic'):
                inner = f'<em>{inner}</em>'
            if style.get('underline'):
                inner = f'<u>{inner}</u>'
            if style.get('strikethrough'):
                inner = f'<s>{inner}</s>'
            css = []
            fg = color_from_style(style, 'foregroundColor')
            bg = color_from_style(style, 'backgroundColor')
            if fg:
                css.append(f'color:{fg}')
            if bg:
                css.append(f'background-color:{bg}')
            if css:
                inner = f'<span style="{";".join(css)}">{inner}</span>'
            link = style.get('link') or {}
            url = link.get('url')
            if url and not should_strip_link(url, self.rules):
                inner = f'<a class="external" href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{inner}</a>'
            return inner
        if 'inlineObjectElement' in element:
            oid = element['inlineObjectElement'].get('inlineObjectId')
            src = self.download_inline_image(oid) if oid else None
            if src:
                obj = self.inline_objects.get(oid, {}) if oid else {}
                emb = (obj.get('inlineObjectProperties') or {}).get('embeddedObject', {})
                size = emb.get('size') or {}
                width = dimension_to_px(size.get('width'))
                height = dimension_to_px(size.get('height'))
                classes = ['doc-image']
                if width and height and max(width, height) <= 40:
                    classes.append('doc-inline-icon')
                styles = []
                if width:
                    styles.append(f'--img-w:{width:g}px')
                if height:
                    styles.append(f'--img-h:{height:g}px')
                style_attr = f' style="{";".join(styles)}"' if styles else ''
                image_html = (f'<img class="{" ".join(classes)}" loading="lazy" '
                              f'src="{src}" alt=""{style_attr}/>')
                # Image links are stored on imageProperties rather than a textRun.
                img_link = (emb.get('imageProperties') or {}).get('link') or {}
                url = img_link.get('url')
                if url and not should_strip_link(url, self.rules):
                    return (f'<a class="external image-link" href="{html.escape(url, quote=True)}" '
                            f'target="_blank" rel="noopener noreferrer">{image_html}</a>')
                return image_html
        if 'horizontalRule' in element:
            # Google Docs source documents may contain horizontal rules directly
            # below section headings. The public wiki already draws its own
            # heading divider with CSS, so rendering the source rule produces
            # an unintended double line. Filter source-authored rules by default.
            if self.rules.get('strip_source_horizontal_rules', True):
                return ''
            return '<hr class="source-horizontal-rule"/>'
        return ''

    def render_paragraph(self, paragraph, force_normal=False):
        text = paragraph_plain_text(paragraph).strip()
        inner = ''.join(self.render_inline(e) for e in paragraph.get('elements', [])).strip()
        if not inner and not text:
            return ''
        depth = named_heading_depth(paragraph)
        if not depth and not force_normal:
            # fallback only for short, numbered paragraphs that look like headings
            if len(text) < 80 and HEADING_RE.match(text):
                depth = heading_depth(text)
        if depth and not force_normal:
            number, title = heading_number_and_title(text)
            depth = heading_depth(text) or depth
            anchor = self.unique_anchor(number, title)
            self.headings.append({'number': number, 'title': title, 'depth': depth, 'anchor': anchor})
            tag = 'h2' if depth <= 2 else ('h3' if depth == 3 else 'h4')
            return (f'<{tag} class="wiki-heading" data-depth="{depth}" id="{anchor}">'
                    f'<button aria-label="문단 접기" aria-expanded="true" class="fold-btn" title="문단 접기" type="button"></button>'
                    f'<a class="internal section-number" href="#{anchor}">{html.escape(number)}</a>'
                    f'<span class="section-title"> {html.escape(title)}</span>'
                    f'<button class="section-edit" title="정적 사이트에서는 편집할 수 없습니다" type="button">[편집]</button>'
                    f'</{tag}>')
        if paragraph.get('bullet'):
            return f'<div class="bullet-item"><span class="bullet">●</span><div>{inner}</div></div>'
        return f'<p>{inner}</p>'

    def table_header_texts(self, table):
        rows = table.get('tableRows', [])
        if not rows:
            return []
        vals = []
        for cell in rows[0].get('tableCells', []):
            vals.append(' '.join(structural_plain_text(c) for c in cell.get('content', [])).strip())
        return vals

    def render_cell(self, cell, header=False):
        parts = []
        for st in cell.get('content', []):
            if 'paragraph' in st:
                parts.append(self.render_paragraph(st['paragraph'], force_normal=True))
            elif 'table' in st:
                parts.append(self.render_table(st['table'], nested=True))
        tag = 'th' if header else 'td'
        return f'<{tag}>{"".join(parts)}</{tag}>'

    def render_table(self, table, nested=False):
        fulltext = structural_plain_text({'table': table})
        normalized_fulltext = normalized_space(fulltext)

        # Entire private tables must disappear, not merely lose their links.
        if any(k in fulltext for k in self.rules.get('private_table_keywords', [])):
            return ''
        for pattern in self.rules.get('private_table_text_patterns', []):
            if re.search(pattern, normalized_fulltext, re.I):
                return ''

        rows = table.get('tableRows', [])
        if not rows:
            return ''
        headers = self.table_header_texts(table)
        normalized_headers = [normalized_space(h) for h in headers]
        private_cols = {normalized_space(k).replace(' ', '') for k in self.rules.get('private_table_columns', [])}
        remove_cols = {
            i for i, h in enumerate(normalized_headers)
            if h.replace(' ', '') in private_cols
        }

        row_count = len(rows)
        col_count = max((len(r.get('tableCells', [])) for r in rows), default=0)
        single_cell = (row_count == 1 and col_count == 1)

        works = ('업로드일' in normalized_headers and
                 ('플랫폼' in normalized_headers or any('플랫' in h for h in normalized_headers)))
        events = ('행사명' in normalized_headers and
                  any(h in {'행사 일시', '일시', '날짜'} for h in normalized_headers))
        logo_gallery = (row_count >= 2 and col_count == 3 and
                        ('팀 이상 버전 2' in normalized_fulltext or '이상고등학교' in normalized_fulltext))
        role_table = ('부서 역할' in normalized_headers and '기타 역할' in normalized_headers)
        drive_shot = ('팀 이상 공유 폴더 내부' in normalized_fulltext)
        requirements = ('레이드모집 생략 요건' in normalized_fulltext or
                        '파티모집 생략 요건' in normalized_fulltext)

        # Google Docs uses short one-cell layout tables for quotation/callout boxes.
        # They are not data tables and must never be promoted to a navy <th>.
        # Long one-cell tables in the rules section are likewise content panels,
        # not headers.  This distinction restores the Espejo-like grey quote UI.
        quote_like = (single_cell and len(normalized_fulltext) <= 260 and
                      not re.search(r'(^|\n)\s*\d+\.', fulltext) and
                      '최소 경고' not in fulltext and '최소 권고' not in fulltext)
        rule_like = (single_cell and not quote_like)

        # Only real multi-row data tables receive header cells.  The previous
        # build made row 1 of every table a <th>, turning quotes/rule panels navy.
        header_first_row = (row_count > 1 and not quote_like and not rule_like)

        out_rows = []
        for ri, row in enumerate(rows):
            cells = []
            for ci, cell in enumerate(row.get('tableCells', [])):
                if ci in remove_cols:
                    continue
                cells.append(self.render_cell(cell, header=(header_first_row and ri == 0)))
            # If filtering removed every cell from a row, do not leave a ghost row.
            if cells:
                out_rows.append('<tr>' + ''.join(cells) + '</tr>')
        if not out_rows:
            return ''

        classes = ['table-scroll']
        if works:
            classes.append('table-works')
        elif events:
            classes.append('table-events')
        elif quote_like:
            classes.append('table-quote')
        elif rule_like:
            classes.append('table-rule')
        elif logo_gallery:
            classes.append('table-logo-gallery')
        elif role_table:
            classes.append('table-role-table')
        elif drive_shot:
            classes.append('table-drive-shot')
        elif requirements:
            classes.append('table-requirements')
        return f'<div class="{" ".join(classes)}"><table>{"".join(out_rows)}</table></div>'

    def align_infobox_link_rows(self, fragment):
        """Keep the tiny source-link icon and its label on one visual baseline.

        Google Docs stores the icon and link text as separate inline elements.
        Browsers then align the bitmap on the text baseline independently, which
        makes the icon look lower/higher than the label. Wrap each icon+link pair
        so CSS can align them as a single inline-flex unit.
        """
        if 'source-link-icon' not in fragment:
            return fragment
        return re.sub(
            r'(<img\b[^>]*class="[^"]*source-link-icon[^"]*"[^>]*/?>)\s*'
            r'(<a\b[^>]*class="[^"]*external[^"]*"[^>]*>.*?</a>)',
            r'<span class="infobox-link-row">\1\2</span>',
            fragment,
            flags=re.I | re.S,
        )

    def render_infobox(self, table):
        rows = table.get('tableRows', [])
        if not rows:
            return None
        out = ['<aside class="infobox-wrap"><table class="infobox">']
        for ri, row in enumerate(rows):
            visible = []
            for cell in row.get('tableCells', []):
                txt = normalized_space(' '.join(structural_plain_text(c) for c in cell.get('content', [])))
                content = ''.join(
                    self.render_paragraph(st['paragraph'], force_normal=True) if 'paragraph' in st else self.render_table(st['table'], nested=True)
                    for st in cell.get('content', [])
                ).strip()
                visible.append((txt, content))

            # Completely empty spacer rows should not create giant blank cells.
            if not visible or not any(txt or content for txt, content in visible):
                continue

            # The projected first row contains the title in the left cell and an
            # empty merged companion cell. Treat it as the infobox caption.
            if ri == 0 and visible and '팀 이상' in visible[0][0] and not any(v[0] or v[1] for v in visible[1:]):
                out.append(f'<caption>{visible[0][1]}</caption>')
                continue

            # Logo/hero rows often have content in only one of the two cells.
            nonempty = [(txt, content) for txt, content in visible if txt or content]
            if len(nonempty) == 1:
                out.append(f'<tr><td class="hero" colspan="2">{nonempty[0][1]}</td></tr>')
                continue

            left = visible[0][1] if len(visible) > 0 else ''
            right = visible[1][1] if len(visible) > 1 else ''
            left = self.align_infobox_link_rows(left)
            right = self.align_infobox_link_rows(right)
            out.append(f'<tr><th>{left}</th><td>{right}</td></tr>')
        out.append('</table></aside>')
        return ''.join(out)


def build_public_model(context, rules, renderer):
    content = context.get('body', {}).get('content', [])
    body_html = []
    info_table = None
    skip_depth = None
    seen_first_heading = False

    for st in content:
        if 'paragraph' in st:
            p = st['paragraph']
            text = paragraph_plain_text(p).strip()
            pdepth = named_heading_depth(p)
            if not pdepth and len(text) < 80 and HEADING_RE.match(text):
                pdepth = heading_depth(text)

            # While inside a private section, skip paragraphs, tables, images and
            # every other structural element until a same/higher-level heading.
            if skip_depth is not None:
                if pdepth is not None and pdepth <= skip_depth:
                    skip_depth = None
                else:
                    continue

            if pdepth is not None and is_private_heading(text, rules):
                skip_depth = pdepth
                continue
            if pdepth is not None and HEADING_RE.match(text):
                seen_first_heading = True
            if not seen_first_heading:
                continue
            rendered = renderer.render_paragraph(p)
            if rendered:
                body_html.append(rendered)
            continue

        # Critical privacy fix: tables that belong to a private section must be
        # skipped as part of that section. The old build only skipped paragraphs.
        if skip_depth is not None:
            continue

        if 'table' in st:
            tbl = st['table']
            txt = structural_plain_text(st)
            if not seen_first_heading and info_table is None and ('팀명' in txt and '업종명' in txt):
                # The source uses one wide layout table: TOC on the left, actual
                # team infobox on the right. Keep only the infobox columns.
                info_table = extract_infobox_table(tbl) or tbl
                continue
            rendered = renderer.render_table(tbl)
            if rendered:
                body_html.append(rendered)
    return ''.join(body_html), info_table


def toc_html(headings):
    lis = []
    for h in headings:
        lis.append(
            f'<li class="toc-item toc-depth-{h["depth"]}">'
            f'<a class="internal toc-entry-link" href="#{h["anchor"]}">'
            f'<span class="toc-number">{html.escape(h["number"])}</span>'
            f'<span class="toc-label"> {html.escape(h["title"])}</span>'
            f'</a></li>'
        )
    return ''.join(lis)


def apply_color_chips(soup):
    # Preserve the user's latest visual fix for hex color descriptions.
    hex_re = re.compile(r'(?<![\w])#(?:[0-9a-fA-F]{6})(?![0-9a-fA-F])')
    target = soup.find(id=re.compile(r'7-1-2-'))
    if not target:
        return
    node = target.find_next_sibling()
    while node:
        if getattr(node, 'name', None) in ('h2', 'h3', 'h4'):
            break
        if getattr(node, 'get_text', None):
            for txt in list(node.find_all(string=True)):
                s = str(txt)
                matches = list(hex_re.finditer(s))
                if not matches:
                    continue
                frag = BeautifulSoup('', 'html.parser')
                pos = 0
                for m in matches:
                    frag.append(s[pos:m.start()])
                    chip = frag.new_tag('span')
                    chip['class'] = ['inline-color-chip']
                    chip['style'] = f'--chip:{m.group(0)}'
                    chip['aria-label'] = m.group(0)
                    frag.append(chip)
                    frag.append(m.group(0))
                    pos = m.end()
                frag.append(s[pos:])
                txt.replace_with(frag)
        node = node.find_next_sibling()


def write_site(template_path, site_assets, output_dir, body_html, infobox_html, headings, meta, rules):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dst_assets = out / 'assets'
    if dst_assets.exists():
        # Keep generated images already downloaded under the output assets folder.
        generated = dst_assets / 'generated'
        temp_gen = None
        if generated.exists():
            temp_gen = out / '.generated-tmp'
            if temp_gen.exists(): shutil.rmtree(temp_gen)
            shutil.move(str(generated), str(temp_gen))
        shutil.rmtree(dst_assets)
        shutil.copytree(site_assets, dst_assets)
        if temp_gen:
            shutil.move(str(temp_gen), str(dst_assets / 'generated'))
    else:
        shutil.copytree(site_assets, dst_assets)

    soup = BeautifulSoup(Path(template_path).read_text(encoding='utf-8'), 'html.parser')
    title = rules.get('source_title') or meta.get('name') or '이상위키'
    soup.title.string = title
    if soup.select_one('.doc-title'):
        soup.select_one('.doc-title').string = title
    if soup.select_one('.doc-meta'):
        modified = meta.get('modifiedTime', '')
        soup.select_one('.doc-meta').string = f'최근 수정 시각: {modified.replace("T", " ").replace("Z", " UTC")}'
    toc = soup.select_one('.toc-list')
    if toc:
        toc.clear()
        frag = BeautifulSoup(toc_html(headings), 'html.parser')
        for c in list(frag.contents): toc.append(c)
    article = soup.select_one('#wikiBody')
    if article:
        article.clear()
        frag = BeautifulSoup(body_html, 'html.parser')
        for c in list(frag.contents): article.append(c)
    if infobox_html:
        old = soup.select_one('.infobox-wrap')
        if old:
            new = BeautifulSoup(infobox_html, 'html.parser').select_one('.infobox-wrap')
            old.replace_with(new)
    apply_color_chips(soup)
    (out / 'index.html').write_text(str(soup), encoding='utf-8')

    # 이상고등학교 본사이트 등 다른 화면에서도 같은 원본을 재사용할 수 있도록
    # 문단별 공개 HTML 조각을 함께 출력한다.
    data_dir = out / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    section_map = {}
    article = soup.select_one('#wikiBody')
    if article:
        heading_tags = article.select('.wiki-heading[id]')
        for h in heading_tags:
            depth = int(h.get('data-depth', '2'))
            num_tag = h.select_one('.section-number')
            title_tag = h.select_one('.section-title')
            parts = []
            sib = h.find_next_sibling()
            while sib is not None:
                if getattr(sib, 'get', None) and 'wiki-heading' in (sib.get('class') or []):
                    next_depth = int(sib.get('data-depth', '2'))
                    if next_depth <= depth:
                        break
                parts.append(str(sib))
                sib = sib.find_next_sibling()
            section_map[h['id']] = {
                'number': num_tag.get_text(strip=True) if num_tag else '',
                'title': title_tag.get_text(' ', strip=True) if title_tag else '',
                'depth': depth,
                'html': ''.join(parts),
            }
    (data_dir / 'sections.json').write_text(json.dumps(section_map, ensure_ascii=False, indent=2), encoding='utf-8')
    rules_section = next((v for k, v in section_map.items() if k.startswith('3-') and v.get('number') == '3.'), None)
    if rules_section:
        (data_dir / 'rules.html').write_text(rules_section['html'], encoding='utf-8')

    (out / 'build-meta.json').write_text(json.dumps({
        'source_document_id': rules.get('master_document_id'),
        'source_modified_time': meta.get('modifiedTime'),
        'source_name': meta.get('name'),
        'public_heading_count': len(headings),
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rules', default='config/public_rules.json')
    ap.add_argument('--template', default='site/template.html')
    ap.add_argument('--assets', default='site/assets')
    ap.add_argument('--out', default='_site')
    args = ap.parse_args()

    rules = load_json(args.rules)
    doc_id = os.environ.get('MASTER_DOC_ID', '').strip() or rules['master_document_id']
    creds = credentials_from_env()
    doc, meta = fetch_document(doc_id, creds)
    context = first_document_tab(doc)

    # Start output first so image downloads land in its final assets folder.
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    renderer = Renderer(context, out, creds, rules)
    body_html, info_table = build_public_model(context, rules, renderer)
    infobox = renderer.render_infobox(info_table) if info_table else None
    write_site(args.template, args.assets, args.out, body_html, infobox, renderer.headings, meta, rules)
    print(f'Built {args.out}/index.html from {meta.get("name")} ({meta.get("modifiedTime")})')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        raise
