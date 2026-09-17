#!/usr/bin/env python3
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlparse

path = Path(sys.argv[1] if len(sys.argv) > 1 else '_site/index.html')
if not path.exists():
    raise SystemExit(f'not found: {path}')
html = path.read_text(encoding='utf-8')
soup = BeautifulSoup(html, 'html.parser')
errors = []

# 1) Private sections must not survive as headings.
for h in soup.select('.wiki-heading'):
    title = h.get_text(' ', strip=True)
    if re.search(r'(^|\s)10\.2\.\s*학생들(?:\s|$)', title) or re.search(r'(^|\s)학생들(?:\s|$)', title):
        errors.append(f'private student section heading leaked: {title}')

# 2) Private columns must be removed structurally, not just unlinked.
for cell in soup.find_all(['th', 'td']):
    value = re.sub(r'\s+', ' ', cell.get_text(' ', strip=True)).strip()
    if value in {'참여진', '참여자', '작업자'}:
        errors.append(f'private table column leaked: {value}')

# 3) Student roster table must be gone in its entirety.
for table in soup.find_all('table'):
    cells = [re.sub(r'\s+', ' ', c.get_text(' ', strip=True)).strip() for c in table.find_all(['th','td'])]
    first = cells[:6]
    has_roster_signature = (
        '기수' in first and '활동명' in first and
        any(v.replace(' ', '') == '한줄메시지' for v in first)
    )
    if has_roster_signature:
        errors.append('private student roster table leaked')

# 4) Google Docs/Drive/Sheets internal URLs must never remain clickable.
for a in soup.find_all('a', href=True):
    href = a['href']
    if href.startswith('#'):
        continue
    host = (urlparse(href).hostname or '').lower()
    if (host == 'drive.google.com' or host == 'docs.google.com' or
            host.endswith('.drive.google.com') or host.endswith('.docs.google.com')):
        errors.append(f'private Google link leaked: {href}')

# Basic build integrity.
if not soup.select_one('#wikiBody'):
    errors.append('wikiBody missing')
if len(soup.select('.wiki-heading')) < 8:
    errors.append('too few headings; build may have failed')
if not soup.select_one('.toc-list'):
    errors.append('toc missing')

if errors:
    print('\n'.join('ERROR: ' + e for e in errors))
    raise SystemExit(1)
print(f'Public validation OK: {path}')
