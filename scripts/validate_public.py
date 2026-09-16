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

# 공개본에 절대로 남으면 안 되는 구조/열
text = soup.get_text(' ', strip=True)
for forbidden in ['10.2. 학생들']:
    if forbidden in text:
        errors.append(f'private section leaked: {forbidden}')

for th in soup.find_all(['th','td']):
    if th.get_text(' ', strip=True) in {'참여진','참여자','작업자'}:
        errors.append(f'private table column leaked: {th.get_text(strip=True)}')

# Google Docs/Drive/Sheets 내부 URL은 외부 사이트에서 실제 링크가 되면 안 됨
for a in soup.find_all('a', href=True):
    href = a['href']
    if href.startswith('#'):
        continue
    host = (urlparse(href).hostname or '').lower()
    if host == 'drive.google.com' or host == 'docs.google.com' or host.endswith('.drive.google.com') or host.endswith('.docs.google.com'):
        errors.append(f'private Google link leaked: {href}')

# 기본 뼈대 검증
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
