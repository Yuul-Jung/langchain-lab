/* 공통 탐색 및 코드 복사 — 페이지 본문을 변경하지 않음 */
(()=>{'use strict';
 const data=window.COURSE||{title:'교육과정',chapters:[]};
 const nav=document.getElementById('course-nav');if(!nav)return;
 const current=document.body.dataset.chapter||'';
 const pageNames=data.chapters||[];
 const home=document.createElement('a');home.className='toplink';home.href='index.html';home.textContent='⌂ '+data.title;nav.append(home);
 let h=document.createElement('h2');h.textContent='전체 장 바로가기';nav.append(h);
 const ul=document.createElement('ul');
 pageNames.forEach(ch=>{let li=document.createElement('li'),a=document.createElement('a');a.href=ch.file;a.textContent=String(ch.number).padStart(2,'0')+'  '+ch.title;if(ch.id===current){a.className='current-chapter active';a.setAttribute('aria-current','page')}li.append(a);ul.append(li)});nav.append(ul);
 const sections=[...document.querySelectorAll('main section[id]')];
 if(sections.length){h=document.createElement('h2');h.textContent='현재 페이지 목차';nav.append(h);const sub=document.createElement('ul');sub.className='toc-sections';sections.forEach(sec=>{let li=document.createElement('li'),a=document.createElement('a');a.href='#'+sec.id;a.textContent=sec.querySelector('h2')?.textContent.trim().replace(/\s+/g,' ')||sec.id;li.append(a);sub.append(li)});nav.append(sub);
 if('IntersectionObserver'in window){const obs=new IntersectionObserver(entries=>{const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top);if(visible[0]){sub.querySelectorAll('a').forEach(x=>x.classList.toggle('active',x.getAttribute('href')==='#'+visible[0].target.id))}},{rootMargin:'-10% 0px -68% 0px',threshold:0});sections.forEach(x=>obs.observe(x))}}
 const idx=pageNames.findIndex(ch=>ch.id===current);const links=document.getElementById('chapter-links');if(links&&idx>=0){const prev=pageNames[idx-1],next=pageNames[idx+1];const add=(ch,label)=>{let a=document.createElement('a');a.href=ch?.file||'index.html';a.textContent=label+(ch?' · '+ch.title:' · 전체 목차');links.append(a)};add(prev,'← 이전');add(next,'다음 →')}
 const toggle=document.getElementById('mobile-menu'),shade=document.getElementById('shade');const close=()=>{nav.classList.remove('open');shade?.classList.remove('open');toggle?.setAttribute('aria-expanded','false')};toggle?.addEventListener('click',()=>{let open=!nav.classList.contains('open');nav.classList.toggle('open',open);shade?.classList.toggle('open',open);toggle.setAttribute('aria-expanded',String(open))});shade?.addEventListener('click',close);nav.addEventListener('click',e=>{if(e.target.closest('a'))close()});document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});
 document.querySelectorAll('.codeblock').forEach(block=>{const pre=block.querySelector('pre');if(!pre)return;const bar=block.querySelector('.codebar');if(!bar)return;const b=document.createElement('button');b.type='button';b.textContent='복사';b.setAttribute('aria-label','코드 복사');b.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(pre.textContent);b.textContent='복사 완료';setTimeout(()=>b.textContent='복사',1200)}catch{b.textContent='복사 실패'}});bar.append(b)});
})();
