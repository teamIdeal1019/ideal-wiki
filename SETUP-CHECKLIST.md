# 설치 체크리스트 — 외부 Docs 없는 단일 원본 버전

- [ ] 패키지 내용을 이상위키 GitHub 저장소 최상위에 업로드
- [ ] Google Cloud에서 Google Docs API 활성화
- [ ] Google Cloud에서 Google Drive API 활성화
- [ ] 읽기 전용 서비스 계정 생성 + JSON 키 발급
- [ ] 내부 원본문서 `1w8uXthXbiAuL--KCP7cq1oH4PJMa-TMRhJEE_6F4A4o`를 서비스 계정 이메일에 **뷰어**로 공유
- [ ] GitHub Secret `GOOGLE_SERVICE_ACCOUNT_JSON` 등록
- [ ] GitHub Pages Source를 **GitHub Actions**로 설정
- [ ] GitHub Actions의 `Sync Ideal Wiki from master Google Doc`를 수동으로 1회 실행
- [ ] 공개 사이트에서 `10.2 학생들`, 참여진, 내부 Google 링크가 없는지 확인
- [ ] GitHub Fine-grained PAT를 이상위키 저장소에 한정해 생성
- [ ] Apps Script 새 프로젝트 생성
- [ ] `apps-script/Code.gs` 붙여넣기
- [ ] `GITHUB_OWNER`, `GITHUB_REPO` 수정
- [ ] Apps Script Script Property `GITHUB_TOKEN` 등록
- [ ] `installTrigger()` 1회 실행 및 권한 승인
- [ ] `forceSync()` 실행 → GitHub Actions가 호출되는지 확인
- [ ] 이후에는 **내부 원본문서만 편집**

## 이 버전에서 하지 않는 것

- 외부용 Google Docs 생성 ❌
- 외부용 Google Docs 수정 ❌
- 외부용 Google Docs와 동기화 ❌
- 내부 원본문서 수정 ❌ (자동화는 읽기만 함)
