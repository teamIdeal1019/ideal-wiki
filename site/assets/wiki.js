const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const toast=(msg)=>{const t=$('#toast');if(!t)return;t.textContent=msg;t.classList.add('show');clearTimeout(window.__tt);window.__tt=setTimeout(()=>t.classList.remove('show'),1900)};

$$('.static-action,.section-edit').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();toast('이 배포본은 읽기 전용 이상위키입니다.')}));
const tocToggle=$('#tocToggle');
if(tocToggle) tocToggle.addEventListener('click',()=>$('#tocBox').classList.toggle('compact'));
const theme=$('#theme');
if(theme) theme.addEventListener('click',()=>{document.body.classList.toggle('dark');localStorage.setItem('idealwiki-dark',document.body.classList.contains('dark')?'1':'0')});
if(localStorage.getItem('idealwiki-dark')==='1') document.body.classList.add('dark');
const backtop=$('#backtop'); if(backtop) backtop.addEventListener('click',()=>scrollTo({top:0,behavior:'smooth'}));

const wikiBody=$('#wikiBody');
const headings=wikiBody?$$('.wiki-heading',wikiBody):[];

function setFoldA11y(h){
  const btn=$('.fold-btn',h);
  if(!btn)return;
  const collapsed=h.classList.contains('section-collapsed');
  btn.setAttribute('aria-expanded',collapsed?'false':'true');
  btn.setAttribute('aria-label',collapsed?'문단 펼치기':'문단 접기');
  btn.title=collapsed?'문단 펼치기':'문단 접기';
}

function recomputeSectionVisibility(){
  if(!wikiBody)return;
  $$('.section-hidden',wikiBody).forEach(el=>el.classList.remove('section-hidden'));

  // A heading owns every following node until the next heading whose depth is
  // the same or higher.  Recalculate from all collapsed headings every time so
  // nested collapse states survive when a parent is folded and reopened.
  headings.filter(h=>h.classList.contains('section-collapsed')).forEach(h=>{
    const depth=Number(h.dataset.depth||2);
    let n=h.nextElementSibling;
    while(n){
      if(n.classList?.contains('wiki-heading') && Number(n.dataset.depth||2)<=depth)break;
      n.classList.add('section-hidden');
      n=n.nextElementSibling;
    }
  });
  headings.forEach(setFoldA11y);
}

headings.forEach(h=>{
  const btn=$('.fold-btn',h);
  if(!btn)return;
  setFoldA11y(h);
  btn.addEventListener('click',e=>{
    e.preventDefault();
    e.stopPropagation();
    h.classList.toggle('section-collapsed');
    recomputeSectionVisibility();
  });
});
const entries=headings.map(h=>({text:(($('.section-number',h)?.textContent||'')+' '+($('.section-title',h)?.textContent||'')).trim(),id:h.id}));

function bindSearch(inputSel,buttonSel,sugSel){
  const q=$(inputSel), btn=$(buttonSel), sug=$(sugSel); if(!q||!btn||!sug)return;
  const show=()=>{const v=q.value.trim().toLowerCase();sug.innerHTML='';if(!v){sug.classList.remove('open');return}const hits=entries.filter(x=>x.text.toLowerCase().includes(v)).slice(0,10);hits.forEach(x=>{const a=document.createElement('a');a.href='#'+x.id;a.textContent=x.text;a.addEventListener('click',()=>sug.classList.remove('open'));sug.appendChild(a)});sug.classList.toggle('open',hits.length>0)};
  q.addEventListener('input',show);q.addEventListener('focus',show);
  btn.addEventListener('click',()=>{const v=q.value.trim().toLowerCase();if(!v)return;const hit=entries.find(x=>x.text.toLowerCase().includes(v));if(hit){location.hash=hit.id;sug.classList.remove('open')}else toast('이 문서의 문단 제목에서 찾지 못했습니다.')});
  q.addEventListener('keydown',e=>{if(e.key==='Enter')btn.click()});
}
bindSearch('#q','#searchBtn','#suggestions');
bindSearch('#qMobile','#searchBtnMobile','#suggestionsMobile');
document.addEventListener('click',e=>{if(!e.target.closest('.search')) $$('.suggestions').forEach(s=>s.classList.remove('open'))});


const backbottom=$('#backbottom');
if(backbottom) backbottom.addEventListener('click',()=>scrollTo({top:document.documentElement.scrollHeight,behavior:'smooth'}));
const floatList=$('.float-list');
if(floatList) floatList.addEventListener('click',()=>{const t=$('#tocBox');if(t)t.scrollIntoView({behavior:'smooth',block:'start'});});
