#!/usr/bin/env python3
"""공통 교육용 GitHub Pages HTML 생성기 — 구성: course.json + content/*.md.

실행: python -m pip install mistune && python build.py
생성: dist/index.html, dist/chXX_*_vNN.html (이미지·스타일·스크립트 내장)
"""
import base64
import html
import json
import re
from pathlib import Path
import mistune

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'dist'
CONFIG = json.loads((ROOT/'course.json').read_text(encoding='utf-8'))
CSS = (ROOT/'assets/site.css').read_text(encoding='utf-8')
SCRIPT = (ROOT/'assets/site.js').read_text(encoding='utf-8')
IMAGE = base64.b64encode((ROOT/'assets/hero-bookshelf.jpg').read_bytes()).decode('ascii')
CSS = CSS.replace("url('hero-bookshelf.jpg')", f"url('data:image/jpeg;base64,{IMAGE}')")
MARKDOWN = mistune.create_markdown(escape=True, plugins=['table'])


def escape(s):
    return html.escape(str(s), quote=True)


def course_chapters():
    chapters=[]
    for raw in CONFIG['chapters']:
        ch=dict(raw)
        ch['file']=f"{ch['slug']}_{ch['version']}.html"
        chapters.append(ch)
    return chapters


CHAPTERS=course_chapters()

def page(title, kicker, desc, chips, body, chapter_id='', footer=''):
    manifest={'title':CONFIG['site_title'], 'chapters':[
        {'id':x['id'],'number':x['number'],'title':x['title'],'file':x['file']} for x in CHAPTERS]}
    chips_html=''.join(f'<span class="chip">{escape(c)}</span>' for c in chips)
    course_data=json.dumps(manifest,ensure_ascii=False).replace('<','\\u003c')
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{escape(desc)}"><title>{escape(title)} · {escape(CONFIG['site_title'])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body data-chapter="{escape(chapter_id)}">
<button type="button" class="mobile-menu" id="mobile-menu" aria-controls="course-nav" aria-expanded="false">☰ 장·목차</button><div class="shade" id="shade"></div>
<header class="hero"><div class="hero-inner"><p class="kicker">{escape(kicker)}</p><h1>{escape(title)}</h1><p>{escape(desc)}</p><div class="chips">{chips_html}</div></div></header>
<div class="wrap"><nav class="toc" id="course-nav" aria-label="장과 절 탐색"></nav><main class="content" id="main-content">{body}<div class="chapter-links" id="chapter-links"></div></main></div>
<footer class="footer">{escape(CONFIG['site_title'])} · {escape(CONFIG['version'])} {escape(footer)} · 실습 결과는 실제 환경에서 검증</footer>
<script>window.COURSE={course_data};</script><script>{SCRIPT}</script></body></html>'''


def render_markdown_sections(md):
    parts=re.split(r'^##\s+(.+?)\s*$',md,flags=re.M)
    if parts[0].strip():
        raise ValueError('장 본문은 ## 절 제목으로 시작해야 합니다.')
    sections=[]
    for n in range(1,len(parts),2):
        title=parts[n].strip()
        content=MARKDOWN(parts[n+1].strip())
        # fenced code needs a consistent header and copy button container
        content=re.sub(r'<pre><code(?: class="language-([^\"]+)")?>(.*?)</code></pre>',
            lambda m:'<div class="codeblock"><div class="codebar"><span>'+escape(m.group(1) or 'TEXT')+'</span></div><pre><code>'+m.group(2)+'</code></pre></div>',content,flags=re.S)
        sections.append(f'<section class="section" id="s{n//2:02d}"><h2><span class="num">{n//2:02d}</span>{escape(title)}</h2>{content}</section>')
    return ''.join(sections),len(sections)


def build():
    OUT.mkdir(exist_ok=True)
    expected={'index.html'}
    cards=[]
    for ch in CHAPTERS:
        source=(ROOT/ch['source']).resolve()
        if ROOT not in source.parents or not source.is_file():
            raise ValueError('잘못된 본문 파일 경로: '+ch['source'])
        body,n=render_markdown_sections(source.read_text(encoding='utf-8'))
        if not n: raise ValueError('본문 절이 없습니다: '+ch['source'])
        html_page=page(f"제{ch['number']:02d}장 · {ch['title']}",f"{CONFIG['course_code']} · CHAPTER {ch['number']:02d}",ch['subtitle'],ch.get('tags',[]),body,ch['id'])
        (OUT/ch['file']).write_text(html_page,encoding='utf-8')
        expected.add(ch['file'])
        cards.append(f'<a class="chapter-card" href="{escape(ch["file"])}"><span>CHAPTER {ch["number"]:02d}</span><b>{escape(ch["title"])}</b><span>{escape(ch["subtitle"])}</span></a>')
    roadmap='<div class="flow">'+''.join(('<div class="down">↓</div>' if i else '')+f'<div class="step"><strong>{ch["number"]:02d} · {escape(ch["title"])}</strong> — {escape(ch["subtitle"])}</div>' for i,ch in enumerate(CHAPTERS))+'</div>'
    content=f'''<section class="section" id="intro"><h2><span class="num">00</span>과정 개요</h2><p>{escape(CONFIG['site_description'])}</p></section>
<section class="section" id="roadmap"><h2><span class="num">01</span>전체 학습 테크트리</h2>{roadmap}</section>
<section class="section" id="chapters"><h2><span class="num">02</span>장별 목차</h2><div class="chapter-grid">{''.join(cards)}</div></section>
<section class="section" id="practice"><h2><span class="num">03</span>학습·검증 원칙</h2><p>개념 → 구조도 → 단계별 코드 → 예상 출력 → 검증 → 완료 기준 순서로 진행합니다. 실제 실행 결과와 교육용 예시는 명확히 구분합니다.</p><p>코드와 설정은 공식 문서를 우선하며, 외부 시스템을 수정하는 작업에는 사용자 승인 및 원본 보호를 적용합니다.</p></section>'''
    (OUT/'index.html').write_text(page(CONFIG['site_title'],CONFIG['course_code'],CONFIG['site_description'],['단계별 학습','실습 중심','GitHub Pages'],content),encoding='utf-8')
    # 최신 버전만 남기기: 출력 디렉터리에 있는 이전 장 HTML 제거, 소스/타 저장소에는 영향 없음
    for p in OUT.glob('*.html'):
        if p.name not in expected: p.unlink()
    print('생성 완료:',len(expected),'개 HTML 파일')
    for name in sorted(expected):print(' ',OUT/name)

if __name__=='__main__':build()
