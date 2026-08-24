# -*- coding: utf-8 -*-
"""
주간 업무 계획 대시보드 게시 스크립트 (jne-briefing-publisher 확장)

동작:
  1) Apps Script 웹 앱({WORKPLAN_API_URL}?api=dashboard)에서 대시보드 데이터를 가져온다.
  2) 자체 완결형 workplan.html을 렌더링한다.
     - 정적 스냅숏(생성 시점 기준)을 먼저 그려 두고,
     - 페이지가 열리면 자바스크립트가 같은 API에서 최신 데이터를 다시 받아 갱신하며,
     - '✏️ 입력하기' 패널에서 부서별 칸을 직접 저장(POST)할 수 있다.
  3) GitHub gist에 workplan.html / workplan.json을 PATCH한다.

환경 변수(Actions secrets):
  WORKPLAN_API_URL  : Apps Script 웹 앱 배포 주소(…/exec)
  GIST_TOKEN        : gist 권한이 있는 GitHub 토큰 (기존과 동일)
  WORKPLAN_GIST_ID  : 게시할 gist ID (없으면 GIST_ID 사용)

로컬 테스트:
  python workplan_publish.py --local out.html --payload sample_payload.json
"""

import argparse
import html
import json
import os
import sys
import datetime

try:
    import requests
except ImportError:  # 로컬 렌더 테스트만 할 때는 requests가 없어도 된다
    requests = None

KST = datetime.timezone(datetime.timedelta(hours=9))
DAY_KO = ["월", "화", "수", "목", "금", "토~일"]


def env_required(name, fallback_name=None):
    v = os.environ.get(name) or (os.environ.get(fallback_name) if fallback_name else None)
    if not v:
        hint = name + (f" (또는 {fallback_name})" if fallback_name else "")
        print(f"[오류] 환경 변수 {hint} 가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)
    return v


def http_get_json(url):
    r = requests.get(url, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r.json()


def fetch_payload(api_url):
    url = api_url + ("&" if "?" in api_url else "?") + "api=dashboard"
    data = http_get_json(url)
    if not data.get("ok"):
        raise RuntimeError("API 응답 오류: " + str(data.get("error")))
    return data


# ---------------------------------------------------------------- SSR helpers

def esc(s):
    return html.escape(str(s if s is not None else ""))


def nl2br(s):
    return esc(s).replace("\n", "<br>")


def md(iso):
    y, m, d = iso.split("-")
    return f"{int(m)}/{int(d)}"


def day_label(week, i):
    if i < 5:
        return f'{DAY_KO[i]} {md(week["dates"][i])}'
    return f'토~일 {md(week["dates"][5])}~{md(week["dates"][6])}'


def chips_html(filled, missing):
    parts = []
    for n in filled:
        parts.append(f'<span class="chip ok">✓ {esc(n)}</span>')
    for n in missing:
        parts.append(f'<span class="chip bad">{esc(n)} 미입력</span>')
    return "".join(parts) or '<span class="muted">부서 정보가 없습니다</span>'


def status_card(title, obj, empty_msg):
    if not obj:
        return (f'<div class="stat"><div class="stat-title">{esc(title)}</div>'
                f'<div class="muted">{esc(empty_msg)}</div></div>')
    total = len(obj.get("filled", [])) + len(obj.get("missing", []))
    done = len(obj.get("filled", []))
    badge_cls = "done" if done == total and total > 0 else "part"
    return (
        f'<div class="stat"><div class="stat-title">{esc(title)} '
        f'<span class="count {badge_cls}">{done}/{total} 부서</span></div>'
        f'<div class="chips">{chips_html(obj.get("filled", []), obj.get("missing", []))}</div></div>'
    )


def week_items_html(week, today_iso):
    rows = []
    for i in range(6):
        items = []
        for dept in week["depts"]:
            text = (dept["days"][i] or "").strip() if i < len(dept["days"]) else ""
            if not text:
                continue
            for line in [ln.strip() for ln in text.split("\n") if ln.strip()]:
                items.append(f'<li><b>{esc(dept["short"])}</b> · {esc(line)}</li>')
        if not items:
            continue
        is_today = (i < 5 and week["dates"][i] == today_iso) or (i == 5 and today_iso in (week["dates"][5], week["dates"][6]))
        is_past = i < 5 and week["dates"][i] < today_iso and not is_today
        cls = "day" + (" today" if is_today else "") + (" past" if is_past else "")
        badge = '<span class="today-badge">오늘</span>' if is_today else ""
        rows.append(f'<div class="{cls}"><div class="day-name">{esc(day_label(week, i))}{badge}</div>'
                    f'<ul>{"".join(items)}</ul></div>')
    if not rows:
        return '<div class="muted">아직 입력된 내용이 없습니다.</div>'
    return "".join(rows)


def week_card(title, week, today_iso):
    if not week:
        return (f'<section class="card"><h2>{esc(title)}</h2>'
                '<div class="muted">아직 이 주의 탭이 없습니다. 입력하기에서 저장하면 자동으로 만들어집니다.</div></section>')
    note_html = ""
    if (week.get("notes") or "").strip():
        note_html = f'<div class="notes"><b>📣 전달·협의사항</b><div>{nl2br(week["notes"])}</div></div>'
    links = []
    if week.get("tabUrl"):
        links.append(f'<a class="mini" href="{esc(week["tabUrl"])}" target="_blank" rel="noopener">시트 탭</a>')
    if week.get("notionPageUrl"):
        links.append(f'<a class="mini" href="{esc(week["notionPageUrl"])}" target="_blank" rel="noopener">노션 페이지</a>')
    return (f'<section class="card"><h2>{esc(title)} <small>{esc(week["label"])} · {esc(week["range"])}</small>'
            f'<span class="links">{"".join(links)}</span></h2>'
            f'{note_html}{week_items_html(week, today_iso)}</section>')


def month_card(mon):
    head = "".join(f"<th>{esc(w)}</th>" for w in mon["weekRanges"])
    body = []
    for d in mon["depts"]:
        cells = "".join(f"<td>{nl2br(w)}</td>" for w in d["weeks"][: len(mon["weekRanges"])])
        body.append(f'<tr><th class="dept">{nl2br(d["name"])}</th>{cells}</tr>')
    note_html = ""
    if (mon.get("notes") or "").strip():
        note_html = f'<div class="notes"><b>📣 월간 전달사항</b><div>{nl2br(mon["notes"])}</div></div>'
    total = len(mon.get("filled", [])) + len(mon.get("missing", []))
    done = len(mon.get("filled", []))
    return (
        f'<details class="card"><summary><h2 style="display:inline">🗓️ {esc(mon["label"])} 월간 사전 계획 '
        f'<span class="count {"done" if done == total and total else "part"}">{done}/{total} 부서</span></h2></summary>'
        f'<div class="chips" style="margin:10px 0">{chips_html(mon.get("filled", []), mon.get("missing", []))}</div>'
        f'{note_html}'
        f'<div class="scroll-x"><table class="mini-table"><tr><th>부서</th>{head}</tr>{"".join(body)}</table></div>'
        f'</details>'
    )


def render_ssr(data):
    today = data.get("todayIso", "")
    parts = ['<div class="stats">']
    parts.append(status_card("이번 주 입력 현황", data.get("thisWeek"), "이번 주 탭이 아직 없습니다"))
    parts.append(status_card("다음 주 입력 현황", data.get("nextWeek"), "다음 주 탭이 아직 없습니다"))
    for mon in data.get("months", []):
        parts.append(status_card(f'{mon["label"]} 월간 사전 계획', mon, ""))
    parts.append("</div>")
    parts.append(week_card("📌 이번 주 할 일", data.get("thisWeek"), today))
    parts.append(week_card("⏭️ 다음 주 할 일", data.get("nextWeek"), today))
    for mon in data.get("months", []):
        parts.append(month_card(mon))
    return "".join(parts)


# ---------------------------------------------------------------- HTML shell

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>주간 업무 계획 대시보드</title>
<style>
:root{--grad1:#667eea;--grad2:#764ba2;--ink:#1f2937;--muted:#6b7280;--line:#e5e7eb;
--ok:#15803d;--okbg:#ecfdf5;--bad:#b91c1c;--badbg:#fef2f2;--amber:#b45309;--amberbg:#fffbeb;}
*{box-sizing:border-box}
body{margin:0;font-family:'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;
background:#f3f4f6;color:var(--ink);line-height:1.55}
.wrap{max-width:1080px;margin:0 auto;padding:14px 14px 60px}
header.top{background:linear-gradient(135deg,var(--grad1),var(--grad2));color:#fff;
border-radius:14px;padding:18px 20px;margin-bottom:14px;box-shadow:0 4px 14px rgba(102,126,234,.35)}
header.top h1{margin:0 0 4px;font-size:1.35rem}
header.top .sub{opacity:.92;font-size:.85rem}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.btn{border:0;border-radius:8px;padding:8px 14px;font-size:.9rem;cursor:pointer;text-decoration:none;
display:inline-block;background:rgba(255,255,255,.18);color:#fff;border:1px solid rgba(255,255,255,.45)}
.btn.primary{background:#fff;color:#4c51bf;font-weight:700}
.btn:hover{filter:brightness(1.06)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px;margin-bottom:14px}
.stat{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.stat-title{font-weight:700;margin-bottom:8px}
.count{font-size:.75rem;border-radius:20px;padding:2px 9px;margin-left:6px;vertical-align:middle}
.count.done{background:var(--okbg);color:var(--ok)}
.count.part{background:var(--amberbg);color:var(--amber)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:.8rem;border-radius:20px;padding:3px 10px;white-space:nowrap}
.chip.ok{background:var(--okbg);color:var(--ok)}
.chip.bad{background:var(--badbg);color:var(--bad);font-weight:700}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:14px}
.card h2{margin:0 0 10px;font-size:1.05rem}
.card h2 small{color:var(--muted);font-weight:400;font-size:.85rem;margin-left:6px}
.links{float:right}
a.mini{font-size:.75rem;color:#4c51bf;border:1px solid #c7d2fe;border-radius:6px;padding:2px 8px;
text-decoration:none;margin-left:6px}
.notes{background:var(--amberbg);border:1px solid #fde68a;border-radius:10px;padding:10px 12px;margin:0 0 12px}
.notes b{display:block;margin-bottom:4px}
.day{display:flex;gap:12px;padding:9px 4px;border-top:1px solid var(--line)}
.day:first-of-type{border-top:0}
.day-name{flex:0 0 92px;font-weight:700;color:#374151}
.day ul{margin:0;padding-left:18px}
.day li{margin:2px 0}
.day.today{background:var(--amberbg);border-radius:8px}
.day.today .day-name{color:var(--amber)}
.day.past{opacity:.55}
.today-badge{display:inline-block;background:var(--amber);color:#fff;font-size:.68rem;
border-radius:6px;padding:1px 6px;margin-left:6px;vertical-align:middle}
.muted{color:var(--muted);font-size:.9rem}
.scroll-x{overflow-x:auto}
.mini-table{border-collapse:collapse;width:100%;font-size:.83rem;min-width:640px}
.mini-table th,.mini-table td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.mini-table tr>th{background:#f9fafb}
.mini-table th.dept{width:110px}
details.card summary{cursor:pointer;list-style:none}
details.card summary::-webkit-details-marker{display:none}
details.card summary:after{content:"펼치기 ▾";float:right;font-size:.78rem;color:var(--muted)}
details[open].card summary:after{content:"접기 ▴"}
#inputPanel{display:none;border:2px solid #c7d2fe;background:#eef2ff}
#inputPanel.open{display:block}
.pillrow{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}
.pill{border:1px solid #c7d2fe;background:#fff;border-radius:20px;padding:5px 13px;cursor:pointer;font-size:.85rem}
.pill.sel{background:#4c51bf;color:#fff;border-color:#4c51bf;font-weight:700}
.field{margin-bottom:10px}
.field label{display:block;font-size:.8rem;font-weight:700;color:#374151;margin-bottom:3px}
.field textarea{width:100%;min-height:52px;border:1px solid var(--line);border-radius:8px;padding:8px;
font-family:inherit;font-size:.9rem;resize:vertical;background:#fff}
.field textarea:focus{outline:2px solid #a5b4fc}
.formgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}
.savebar{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
.btn.save{background:#4c51bf;color:#fff;font-weight:700;padding:10px 22px}
.btn.ghost{background:#fff;color:#4c51bf;border:1px solid #c7d2fe}
#pinBox{border:1px solid var(--line);border-radius:8px;padding:8px;font-size:.9rem}
#toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:#111827;color:#fff;
padding:10px 18px;border-radius:10px;font-size:.9rem;opacity:0;transition:opacity .3s;pointer-events:none;
max-width:90vw;text-align:center}
#toast.show{opacity:.95}
footer{color:var(--muted);font-size:.78rem;text-align:center;margin-top:18px}
@media (max-width:560px){.day{flex-direction:column;gap:2px}.day-name{flex:none}.links{float:none;display:block;margin-top:4px}}
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <h1>📋 주간 업무 계획 대시보드</h1>
  <div class="sub" id="subline">__SUBLINE__</div>
  <div class="toolbar">
    <button class="btn primary" id="btnInput" style="display:none" onclick="togglePanel()">✏️ 입력하기</button>
    <button class="btn" id="btnRefresh" style="display:none" onclick="refresh(true)">🔄 새로 고침</button>
    <a class="btn" href="__SHEET_URL__" target="_blank" rel="noopener">📗 시트 열기</a>
    <a class="btn" href="__NOTION_URL__" target="_blank" rel="noopener">📘 노션 열기</a>
  </div>
</header>

<section class="card" id="inputPanel">
  <h2>✏️ 업무 입력 <small>부서와 주를 고르고 칸을 채운 뒤 저장을 누르세요</small></h2>
  <div id="inputBody"></div>
</section>

<main id="content">__SSR__</main>

<footer id="foot">정적 스냅숏 생성: __GENERATED__ · 입력 내용은 구글 시트에 저장되고, 노션에는 10분 안에 자동 반영됩니다.</footer>
</div>
<div id="toast"></div>

<script>
var API = "__API_URL__";
var DATA = __DATA_JSON__;
var st = { week: 'next', dept: null, busy: false };

function esc(s){var d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}
function md(iso){var p=iso.split('-');return (+p[1])+'/'+(+p[2]);}
var DAY_KO=['월','화','수','목','금','토~일'];
function dayLabel(w,i){return i<5? DAY_KO[i]+' '+md(w.dates[i]) : '토~일 '+md(w.dates[5])+'~'+md(w.dates[6]);}
function nl2br(s){return esc(s).replace(/\n/g,'<br>');}

function chipsHtml(filled,missing){
  var h='';
  (filled||[]).forEach(function(n){h+='<span class="chip ok">✓ '+esc(n)+'</span>';});
  (missing||[]).forEach(function(n){h+='<span class="chip bad">'+esc(n)+' 미입력</span>';});
  return h||'<span class="muted">부서 정보가 없습니다</span>';
}
function statCard(title,o,emptyMsg){
  if(!o) return '<div class="stat"><div class="stat-title">'+esc(title)+'</div><div class="muted">'+esc(emptyMsg)+'</div></div>';
  var total=(o.filled||[]).length+(o.missing||[]).length, done=(o.filled||[]).length;
  var cls=(done===total&&total>0)?'done':'part';
  return '<div class="stat"><div class="stat-title">'+esc(title)+' <span class="count '+cls+'">'+done+'/'+total+' 부서</span></div>'
    +'<div class="chips">'+chipsHtml(o.filled,o.missing)+'</div></div>';
}
function weekItems(w,today){
  var out='';
  for(var i=0;i<6;i++){
    var items='';
    (w.depts||[]).forEach(function(d){
      var t=(d.days[i]||'').trim();
      if(!t)return;
      t.split(/\n/).forEach(function(line){
        line=line.trim(); if(!line)return;
        items+='<li><b>'+esc(d.short)+'</b> · '+esc(line)+'</li>';
      });
    });
    if(!items)continue;
    var isToday=(i<5&&w.dates[i]===today)||(i===5&&(today===w.dates[5]||today===w.dates[6]));
    var isPast=i<5&&w.dates[i]<today&&!isToday;
    out+='<div class="day'+(isToday?' today':'')+(isPast?' past':'')+'"><div class="day-name">'+esc(dayLabel(w,i))
      +(isToday?'<span class="today-badge">오늘</span>':'')+'</div><ul>'+items+'</ul></div>';
  }
  return out||'<div class="muted">아직 입력된 내용이 없습니다.</div>';
}
function weekCard(title,w,today){
  if(!w) return '<section class="card"><h2>'+esc(title)+'</h2><div class="muted">아직 이 주의 탭이 없습니다. 입력하기에서 저장하면 자동으로 만들어집니다.</div></section>';
  var links='';
  if(w.tabUrl) links+='<a class="mini" href="'+esc(w.tabUrl)+'" target="_blank" rel="noopener">시트 탭</a>';
  if(w.notionPageUrl) links+='<a class="mini" href="'+esc(w.notionPageUrl)+'" target="_blank" rel="noopener">노션 페이지</a>';
  var notes=(w.notes||'').trim()?'<div class="notes"><b>📣 전달·협의사항</b><div>'+nl2br(w.notes)+'</div></div>':'';
  return '<section class="card"><h2>'+esc(title)+' <small>'+esc(w.label)+' · '+esc(w.range)+'</small><span class="links">'+links+'</span></h2>'
    +notes+weekItems(w,today)+'</section>';
}
function monthCard(m){
  var head='';m.weekRanges.forEach(function(x){head+='<th>'+esc(x)+'</th>';});
  var body='';
  (m.depts||[]).forEach(function(d){
    var cells='';
    for(var i=0;i<m.weekRanges.length;i++){cells+='<td>'+nl2br(d.weeks[i]||'')+'</td>';}
    body+='<tr><th class="dept">'+nl2br(d.name)+'</th>'+cells+'</tr>';
  });
  var total=(m.filled||[]).length+(m.missing||[]).length, done=(m.filled||[]).length;
  var notes=(m.notes||'').trim()?'<div class="notes"><b>📣 월간 전달사항</b><div>'+nl2br(m.notes)+'</div></div>':'';
  return '<details class="card"><summary><h2 style="display:inline">🗓️ '+esc(m.label)+' 월간 사전 계획 '
    +'<span class="count '+((done===total&&total)?'done':'part')+'">'+done+'/'+total+' 부서</span></h2></summary>'
    +'<div class="chips" style="margin:10px 0">'+chipsHtml(m.filled,m.missing)+'</div>'+notes
    +'<div class="scroll-x"><table class="mini-table"><tr><th>부서</th>'+head+'</tr>'+body+'</table></div></details>';
}
function renderAll(){
  var d=DATA, today=d.todayIso||'';
  var h='<div class="stats">';
  h+=statCard('이번 주 입력 현황',d.thisWeek,'이번 주 탭이 아직 없습니다');
  h+=statCard('다음 주 입력 현황',d.nextWeek,'다음 주 탭이 아직 없습니다');
  (d.months||[]).forEach(function(m){h+=statCard(m.label+' 월간 사전 계획',m,'');});
  h+='</div>';
  h+=weekCard('📌 이번 주 할 일',d.thisWeek,today);
  h+=weekCard('⏭️ 다음 주 할 일',d.nextWeek,today);
  (d.months||[]).forEach(function(m){h+=monthCard(m);});
  document.getElementById('content').innerHTML=h;
  renderInput();
}
function toast(msg){
  var t=document.getElementById('toast');
  t.textContent=msg;t.classList.add('show');
  clearTimeout(t._h);t._h=setTimeout(function(){t.classList.remove('show');},3200);
}
function setSub(extra){
  var el=document.getElementById('subline');
  el.textContent='오늘 '+(DATA.todayIso||'')+' · '+extra;
}
function refresh(manual){
  if(!API){return;}
  fetch(API+'?api=dashboard').then(function(r){return r.json();}).then(function(j){
    if(j&&j.ok!==false&&j.thisWeek!==undefined){
      DATA=j;renderAll();
      setSub('실시간 자료 ('+new Date().toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'})+' 기준)');
      if(manual)toast('최신 내용으로 갱신했습니다.');
    } else if(manual){toast('갱신에 실패했습니다: '+((j&&j.error)||'알 수 없는 오류'));}
  }).catch(function(){ if(manual)toast('네트워크 연결을 확인해 주세요. 화면은 마지막 스냅숏입니다.'); });
}

/* ---------------- 입력 패널 ---------------- */
function weekObj(which){return which==='this'?DATA.thisWeek:DATA.nextWeek;}
function deptSource(){
  var w=weekObj(st.week)||weekObj(st.week==='this'?'next':'this');
  if(w&&w.depts&&w.depts.length)return w.depts;
  if(DATA.months&&DATA.months.length&&DATA.months[0].depts.length)return DATA.months[0].depts;
  return [];
}
function togglePanel(){
  var p=document.getElementById('inputPanel');
  p.classList.toggle('open');
  if(p.classList.contains('open')){renderInput();p.scrollIntoView({behavior:'smooth'});}
}
function selWeek(w){st.week=w;renderInput();}
function selDept(name){st.dept=name;renderInput();}
function renderInput(){
  var box=document.getElementById('inputBody');
  if(!box||!document.getElementById('inputPanel').classList.contains('open'))return;
  var depts=deptSource();
  if(!depts.length){box.innerHTML='<div class="muted">아직 부서 목록을 불러오지 못했습니다. 시트에서 직접 입력해 주세요.</div>';return;}
  var h='<div class="pillrow">'
    +'<span class="pill'+(st.week==='this'?' sel':'')+'" onclick="selWeek(\'this\')">이번 주'+(DATA.thisWeek?' ('+DATA.thisWeek.label+')':'')+'</span>'
    +'<span class="pill'+(st.week==='next'?' sel':'')+'" onclick="selWeek(\'next\')">다음 주'+(DATA.nextWeek?' ('+DATA.nextWeek.label+')':'')+'</span>'
    +'</div><div class="pillrow">';
  depts.forEach(function(d){
    h+='<span class="pill'+(st.dept===d.name?' sel':'')+'" onclick="selDept(\''+esc(d.name).replace(/'/g,"\\'").replace(/\n/g,'\\n')+'\')">'+esc(d.short)+'</span>';
  });
  h+='</div>';
  if(st.dept){
    var w=weekObj(st.week);
    var mine=null;
    depts.forEach(function(d){if(d.name===st.dept)mine=d;});
    if(w){ (w.depts||[]).forEach(function(d){if(d.name===st.dept)mine=d;}); }
    var days=(w&&mine&&mine.days)?mine.days:['','','','','',''];
    h+='<div class="formgrid">';
    for(var i=0;i<6;i++){
      var label=w?dayLabel(w,i):DAY_KO[i];
      h+='<div class="field"><label>'+esc(label)+'</label><textarea id="day'+i+'">'+esc(days[i]||'')+'</textarea></div>';
    }
    h+='</div>';
    h+='<div class="field"><label>📣 전달·협의사항 (부서 공통 칸입니다. 기존 내용에 덧붙여 주세요)</label>'
      +'<textarea id="noteBox">'+esc(w?(w.notes||''):'')+'</textarea></div>';
    h+='<div class="savebar"><button class="btn save" onclick="saveAll()">💾 저장</button>'
      +(DATA.pinRequired?'<input id="pinBox" type="password" placeholder="입력 비밀번호" value="'+esc(localStorage.getItem('wp_pin')||'')+'">':'')
      +'<button class="btn ghost" onclick="togglePanel()">닫기</button>'
      +'<span class="muted">저장하면 시트에 기록되고 10분 안에 노션에 반영됩니다.</span></div>';
  } else {
    h+='<div class="muted">부서를 선택해 주세요.</div>';
  }
  box.innerHTML=h;
}
function post(body){
  if(DATA.pinRequired){
    var pinEl=document.getElementById('pinBox');
    body.pin=pinEl?pinEl.value:'';
    try{localStorage.setItem('wp_pin',body.pin);}catch(e){}
  }
  return fetch(API,{method:'POST',body:JSON.stringify(body)}).then(function(r){return r.json();});
}
function saveAll(){
  if(st.busy)return;
  var w=weekObj(st.week);
  var mine=null;
  if(w){(w.depts||[]).forEach(function(d){if(d.name===st.dept)mine=d;});}
  var jobs=[];
  for(var i=0;i<6;i++){
    var v=document.getElementById('day'+i).value;
    var old=(w&&mine)?(mine.days[i]||''):'';
    if(v!==old)jobs.push({action:'save',week:st.week,dept:st.dept,day:i,text:v});
  }
  var noteV=document.getElementById('noteBox').value;
  var noteOld=w?(w.notes||''):'';
  if(noteV!==noteOld)jobs.push({action:'saveNote',week:st.week,text:noteV});
  if(!jobs.length){toast('바뀐 내용이 없습니다.');return;}
  st.busy=true;toast('저장 중… ('+jobs.length+'건)');
  var idx=0,lastData=null,failed=null;
  function next(){
    if(idx>=jobs.length){
      st.busy=false;
      if(lastData){DATA=lastData;renderAll();}
      else refresh(false);
      toast(failed?('일부 저장 실패: '+failed):'저장되었습니다. 노션에는 10분 안에 반영됩니다.');
      return;
    }
    post(jobs[idx]).then(function(j){
      if(!j.ok){failed=j.error||'오류';}
      if(j.data)lastData=j.data;
      idx++;next();
    }).catch(function(){failed='네트워크 오류';idx++;next();});
  }
  next();
}

/* ---------------- 시작 ---------------- */
(function init(){
  if(API){
    document.getElementById('btnInput').style.display='';
    document.getElementById('btnRefresh').style.display='';
    renderAll();
    refresh(false);
    setInterval(function(){refresh(false);},5*60*1000);
  }
})();
</script>
</body>
</html>
"""


def render_html(data, api_url, generated_label):
    html_out = (
        TEMPLATE
        .replace("__SUBLINE__", esc(f"오늘 {data.get('todayIso', '')} · 정적 스냅숏 {generated_label} 기준 (열리면 자동 갱신)"))
        .replace("__SHEET_URL__", esc(data.get("sheetUrl", "#")))
        .replace("__NOTION_URL__", esc(data.get("notionDbUrl", "#")))
        .replace("__SSR__", render_ssr(data))
        .replace("__GENERATED__", esc(generated_label))
        .replace("__API_URL__", (api_url or "").replace('"', ""))
        .replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    )
    return html_out


def patch_gist(token, gist_id, files):
    r = requests.patch(
        f"https://api.github.com/gists/{gist_id}",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
        json={"files": {name: {"content": content} for name, content in files.items()}},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="gist에 올리지 않고 이 경로에 HTML만 저장")
    ap.add_argument("--payload", help="API 대신 이 JSON 파일을 데이터로 사용(테스트용)")
    ap.add_argument("--api-url", help="환경 변수 대신 사용할 API 주소(테스트용)")
    args = ap.parse_args()

    api_url = args.api_url or os.environ.get("WORKPLAN_API_URL", "")
    if args.payload:
        with open(args.payload, encoding="utf-8") as f:
            data = json.load(f)
    else:
        if not api_url:
            env_required("WORKPLAN_API_URL")
        data = fetch_payload(api_url)

    now = datetime.datetime.now(KST)
    generated = now.strftime("%m/%d %H:%M")
    html_out = render_html(data, api_url, generated)

    if args.local:
        with open(args.local, "w", encoding="utf-8") as f:
            f.write(html_out)
        print(f"[완료] 로컬 렌더링: {args.local} ({len(html_out):,}자)")
        return

    token = env_required("GIST_TOKEN")
    gist_id = env_required("WORKPLAN_GIST_ID", "GIST_ID")
    patch_gist(token, gist_id, {
        "workplan.html": html_out,
        "workplan.json": json.dumps(data, ensure_ascii=False, indent=1),
    })
    print(f"[완료] gist {gist_id} 에 workplan.html / workplan.json 게시 ({now.isoformat()})")


if __name__ == "__main__":
    main()
