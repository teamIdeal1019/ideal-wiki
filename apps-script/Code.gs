/**
 * 팀 이상 이상위키 — 단일 원본 → GitHub Pages 자동 배포
 *
 * 사람이 직접 수정하는 곳은 MASTER_DOC_ID의 내부용 Google Docs 하나뿐입니다.
 * Apps Script는 문서 내용을 복사/편집하지 않습니다.
 * 5분마다 수정 시각만 확인한 뒤, 실제 변경이 있을 때만 GitHub Actions를 호출합니다.
 */
const MASTER_DOC_ID = '1w8uXthXbiAuL--KCP7cq1oH4PJMa-TMRhJEE_6F4A4o';

const GITHUB_OWNER = 'CHANGE_ME';
const GITHUB_REPO = 'CHANGE_ME';
const DISPATCH_EVENT = 'wiki-source-updated';

/** 5분 변경 감지 트리거를 설치합니다. 처음 설치할 때는 현재 수정 시각을 기준점으로 저장합니다. */
function installTrigger() {
  removeTriggers_('checkWikiSource');
  ScriptApp.newTrigger('checkWikiSource').timeBased().everyMinutes(5).create();

  const modified = DriveApp.getFileById(MASTER_DOC_ID).getLastUpdated().toISOString();
  PropertiesService.getScriptProperties().setProperty('LAST_MASTER_MODIFIED', modified);
  Logger.log(`트리거 설치 완료. 기준 수정 시각: ${modified}`);
  Logger.log('즉시 배포 테스트가 필요하면 forceSync()를 실행하세요.');
}

/** 이 프로젝트가 만든 변경 감지 트리거를 제거합니다. */
function uninstallTriggers() {
  removeTriggers_('checkWikiSource');
  Logger.log('변경 감지 트리거를 제거했습니다.');
}

/** 문서 변경 여부와 관계없이 GitHub 공개본 빌드를 즉시 1회 호출합니다. */
function forceSync() {
  syncIfNeeded_(true);
}

/** 시간 기반 트리거가 호출하는 함수입니다. */
function checkWikiSource() {
  syncIfNeeded_(false);
}

function syncIfNeeded_(force) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return;

  try {
    const props = PropertiesService.getScriptProperties();
    const modified = DriveApp.getFileById(MASTER_DOC_ID).getLastUpdated().toISOString();
    const last = props.getProperty('LAST_MASTER_MODIFIED');

    if (!force && last === modified) {
      Logger.log('변경 없음 — GitHub 호출 생략');
      return;
    }

    // GitHub 호출이 성공한 뒤에만 기준 시각을 갱신한다.
    // 실패하면 다음 트리거에서 다시 시도할 수 있다.
    dispatchGitHub_(modified);
    props.setProperty('LAST_MASTER_MODIFIED', modified);
    Logger.log(`GitHub 공개본 빌드 호출 완료: ${modified}`);
  } finally {
    lock.releaseLock();
  }
}

function dispatchGitHub_(modified) {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('GITHUB_TOKEN');

  if (!token) {
    throw new Error('Apps Script의 Script Property에 GITHUB_TOKEN을 등록하세요.');
  }
  if (GITHUB_OWNER === 'CHANGE_ME' || GITHUB_REPO === 'CHANGE_ME') {
    throw new Error('Code.gs 상단의 GITHUB_OWNER / GITHUB_REPO를 실제 저장소 값으로 변경하세요.');
  }

  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/dispatches`;
  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    muteHttpExceptions: true,
    contentType: 'application/json',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    payload: JSON.stringify({
      event_type: DISPATCH_EVENT,
      client_payload: {
        modified_time: modified,
        source: 'google-apps-script',
        master_document_id: MASTER_DOC_ID,
      },
    }),
  });

  const code = response.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error(`GitHub repository_dispatch 실패 (${code}): ${response.getContentText()}`);
  }
}

function removeTriggers_(handlerName) {
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === handlerName) {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}
