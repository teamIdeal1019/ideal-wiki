# 팀 이상 이상위키 — 단일 원본 직접 배포 자동화

이 버전은 **외부용 Google Docs를 만들거나 수정하지 않습니다.**
사람이 편집하는 문서는 내부용 원본 Google Docs **한 개뿐**입니다.

- 내부 원본 Google Docs ID: `1w8uXthXbiAuL--KCP7cq1oH4PJMa-TMRhJEE_6F4A4o`
- 외부용 Google Docs: **자동화에서 완전히 제외됨**

## 최종 구조

```text
내부용 이상위키 Google Docs
(유일한 편집 원본)
        │
        │ Apps Script가 5분마다 "수정 시각"만 확인
        ▼
GitHub repository_dispatch
        │
        ▼
GitHub Actions
        │
        ├─ Google Docs API로 내부 원본 읽기
        ├─ 공개 필터 적용
        ├─ 이미지/표/링크를 위키 HTML로 변환
        ├─ 개인정보·내부 URL 유출 검사
        └─ 검사 통과 시 GitHub Pages 배포
                │
                └─ data/rules.html 생성
                   이상고등학교 교칙 페이지에서 재사용 가능
```

외부용 문서와 사이트에 같은 내용을 다시 작성할 필요가 없습니다.

---

## 공개 필터

현재 내부/외부 문서의 실제 차이를 기준으로 기본 필터가 들어 있습니다.

### 공개 유지

- 1. 개요
- 2. 로고
- 3. 규칙 전체
- 4. 개설 부서
- 5. 취급 콘텐츠
- 6. 디스코드 채널의 설명
- 7. 구글 드라이브의 구조 및 사용법 설명
- 8. 반장·부반장 / 프로젝트 기획 프로세스
- 9. 작품의 날짜·플랫폼·썸네일·작품명·공개 영상 링크
- 9.2. 행사
- 10. 세계관 / 이상고등학교 설명

### 외부 공개본에서 자동 제거

- `10.2. 학생들` 문단 전체
- 제목이 `🔒` 또는 `[내부]`로 표시된 문단 전체
- 작품표의 `참여진`, `참여자`, `작업자` 열
- `포스타입 예비 계정` 같은 내부 전용 표
- `drive.google.com`, `docs.google.com`으로 향하는 실제 링크
  - 표시 텍스트와 아이콘은 남을 수 있지만 클릭 주소는 제거됩니다.

규칙은 `config/public_rules.json`에서 관리합니다.

> 안전 원칙: 공개해야 할 것을 일일이 허용하는 구조가 아니라, 확인된 내부 영역과 내부 URL을 빌드 단계에서 제거한 뒤 **별도의 유출 검사**를 한 번 더 통과시킵니다.

---

# 설치

## 1. GitHub 저장소에 업로드

이 패키지의 폴더 내용 전체를 외부 이상위키용 GitHub 저장소 최상위에 올립니다.

필수 구조:

```text
.github/workflows/sync-wiki.yml
apps-script/Code.gs
apps-script/appsscript.json
config/public_rules.json
scripts/build_site.py
scripts/validate_public.py
site/template.html
site/assets/
```

## 2. Google Cloud 서비스 계정

GitHub Actions는 내부 원본문서를 **읽기만** 합니다.

1. Google Cloud 프로젝트 생성
2. Google Docs API 활성화
3. Google Drive API 활성화
4. 서비스 계정 생성
5. 서비스 계정 JSON 키 생성
6. 내부 원본문서를 서비스 계정 이메일에 **뷰어** 권한으로 공유

서비스 계정에 편집자 권한을 줄 필요가 없습니다.

## 3. GitHub Secret

GitHub 저장소에서:

`Settings → Secrets and variables → Actions → New repository secret`

이름:

```text
GOOGLE_SERVICE_ACCOUNT_JSON
```

값에는 서비스 계정 JSON의 전체 내용을 붙여넣습니다.
JSON 키 파일을 저장소에 직접 업로드하면 안 됩니다.

## 4. GitHub Pages

`Settings → Pages → Build and deployment → Source → GitHub Actions`

그 후 Actions 탭에서:

`Sync Ideal Wiki from master Google Doc → Run workflow`

을 한 번 실행합니다.

GitHub Actions는 다음 순서로 동작합니다.

```text
내부 원본 읽기
→ 공개 필터
→ index.html / assets / data 생성
→ validate_public.py 유출 검사
→ 통과 시 Pages 배포
```

검사에 실패하면 새 공개본은 배포되지 않으므로 기존 정상 사이트가 유지됩니다.

## 5. Apps Script 변경 감지

GitHub Actions를 5분마다 무조건 실행하지 않습니다.
Apps Script가 내부 원본의 **수정 시각만** 5분마다 비교합니다.

1. `script.google.com`에서 새 프로젝트 생성
2. `apps-script/Code.gs`를 붙여넣기
3. 가능하면 프로젝트 설정에서 `appsscript.json`을 표시하고 패키지의 파일 내용으로 교체
4. `Code.gs` 상단의 다음 두 값 수정

```javascript
const GITHUB_OWNER = '내 GitHub 아이디';
const GITHUB_REPO = '이상위키 저장소명';
```

5. Apps Script `프로젝트 설정 → 스크립트 속성`에 등록

```text
GITHUB_TOKEN = GitHub Fine-grained PAT
```

6. `installTrigger()`를 1회 실행
7. 권한 승인
8. `forceSync()`를 실행해 즉시 배포 테스트

그 뒤부터는 실제 원본문서가 바뀌었을 때만 GitHub Actions가 호출됩니다.

### GitHub PAT

Fine-grained personal access token은 **이상위키 저장소 하나만** 접근하도록 제한하고, repository dispatch를 보낼 수 있는 최소 권한으로 설정하세요. 토큰을 `Code.gs`에 직접 적지 말고 Script Property에만 저장합니다.

---

# 앞으로 위키를 수정하는 방법

## 일반 공개 내용

그냥 내부 원본문서를 수정합니다.

예:

```text
3. 규칙
  프로젝트 관련 규정
  15. 새 규칙 ...
```

저장 후 최대 약 5분 뒤 변경이 감지되고 공개 위키가 재빌드됩니다.

## 새로운 내부 전용 문단

제목에 다음 중 하나를 붙입니다.

```text
🔒 관리자용 처리 절차
```

또는

```text
[내부] 관리자용 처리 절차
```

해당 제목부터 다음 같은 단계 이상의 제목 전까지 외부 공개본에서 제외됩니다.
표와 이미지도 함께 제외됩니다.

## 새로운 내부 전용 표 열

`config/public_rules.json`의 `private_table_columns`에 열 이름을 추가합니다.

예:

```json
"private_table_columns": [
  "참여진",
  "참여자",
  "작업자",
  "내부 메모"
]
```

---

# 이상고등학교 사이트와 규칙 공유

빌드 결과에는:

```text
data/sections.json
data/rules.html
```

이 생성됩니다.

`data/rules.html`은 같은 내부 원본문서의 **3. 규칙**에서 공개 가능한 부분만 추출한 결과입니다.
학교 사이트에 `site/school-site-example.js`와 같은 방식으로 연결하면 교칙을 따로 작성할 필요가 없습니다.

---

# 외부용 Google Docs는 어떻게 하나?

이 자동화는 외부용 Google Docs의 ID를 **알지도 않고, 읽지도 않고, 수정하지도 않습니다.**
기존 외부 문서는 필요하면 기록용으로 그대로 두거나 보관해도 됩니다.

앞으로의 공개 원본은 GitHub Pages에 생성되는 외부 이상위키입니다.
따라서 운영 원칙은 하나입니다.

> **내부용 Google Docs만 수정한다. GitHub Pages 공개본은 자동 생성한다.**

---

# 주요 파일

- `.github/workflows/sync-wiki.yml` — 공개본 빌드/검사/Pages 배포
- `apps-script/Code.gs` — 원본 수정 시각 감지 후 GitHub 호출만 수행
- `config/public_rules.json` — 공개/비공개 필터 정책
- `scripts/build_site.py` — Google Docs → 나무위키형 HTML 변환
- `scripts/validate_public.py` — 공개본 유출 방지 검사
- `site/template.html` / `site/assets/` — 현재 완성한 이상위키 UI
- `site/school-site-example.js` — 이상고등학교에서 규칙 재사용 예시
