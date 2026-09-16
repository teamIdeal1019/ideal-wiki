/*
  이상고등학교 사이트에서 규칙을 중복 작성하지 않는 예시.
  외부 위키가 같은 도메인의 /wiki/에 배포되어 있다면 그대로 사용할 수 있습니다.
*/
async function loadIdealRules() {
  const res = await fetch('/wiki/data/rules.html', { cache: 'no-store' });
  if (!res.ok) throw new Error(`규칙 불러오기 실패: ${res.status}`);
  document.querySelector('#rules-from-wiki').innerHTML = await res.text();
}

loadIdealRules().catch(console.error);
