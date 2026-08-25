# -*- coding: utf-8 -*-
"""
briefing.html 안에서 가장 넓은 자리를 차지하는 '주간 업무 계획' 구역.

각 선생님 PC의 학사일정브리핑.exe는 gist의 briefing.html만 내려받아 표시하므로,
주간 업무 계획도 이 파일 안에 함께 실려 있어야 선생님들이 볼 수 있습니다.

화면은 세 덩어리로 나누어 놓았습니다.
  1) 입력 현황: 이번 주와 다음 주, 다음 달 사전 계획을 부서 수로 알려 줍니다.
  2) 주요일정: 달력에서 내려온 날짜별 정보이므로 이번 주와 다음 주를 두 줄로 붙여 놓습니다.
  3) 부서별 계획: 부서마다 한 장의 카드를 만들고, 그 안에 이번 주와 다음 주를 함께 담습니다.
     아직 아무것도 쓰지 않은 부서도 카드를 만들어 두어야 누가 남았는지 한눈에 보입니다.

동작 방식은 두 단계입니다.
  1) 발행 시각의 자료를 미리 그려 넣습니다. 자바스크립트가 동작하지 않는
     환경에서도 입력 현황과 이번 주·다음 주 할 일이 그대로 보입니다.
  2) 자바스크립트가 동작하면 Apps Script API에서 최신 자료를 다시 받아 다시 그리고,
     '여기서 바로 입력' 단추와 입력 패널을 함께 엽니다.

환경 변수 WORKPLAN_API_URL이 없거나 API 호출에 실패하면 빈 문자열을 돌려주므로,
기존 브리핑 발행에는 아무 영향을 주지 않습니다.
"""

import html
import json
import os

import requests

DAY_KO = ['월', '화', '수', '목', '금', '토~일']
MAJOR_NAME = '주요일정'

# 부서마다 다른 색을 주어 카드가 여러 장 놓여도 서로 구분되게 한다.
DEPT_TONES = ['#a95a08', '#0e6f61', '#3f5fa8', '#8a3b62', '#4a6b23', '#7a4a1f']


def _tone(idx):
    return DEPT_TONES[idx % len(DEPT_TONES)]


# ------------------------------------------------------------------ 값 다듬기

def _esc(s):
    return html.escape(str(s if s is not None else ''))


def _nl2br(s):
    return _esc(s).replace('\n', '<br>')


def _md(iso):
    y, m, d = str(iso).split('-')
    return '%d/%d' % (int(m), int(d))


def _day_label(week, i):
    if i < 5:
        return '%s %s' % (DAY_KO[i], _md(week['dates'][i]))
    return '토~일 %s~%s' % (_md(week['dates'][5]), _md(week['dates'][6]))


def _is_today(week, i, today_iso):
    dates = (week or {}).get('dates', [])
    if not dates:
        return False
    if i < 5:
        return dates[i] == today_iso
    return today_iso in (dates[5], dates[6])


def _lines_of(dept, i):
    days = (dept or {}).get('days', [])
    text = (days[i] or '').strip() if i < len(days) else ''
    return [ln.strip() for ln in text.split('\n') if ln.strip()]


def _find_dept(week, name):
    for d in (week or {}).get('depts', []):
        if (d.get('name') or '').strip() == name:
            return d
    return None


def _dept_index(data):
    """이번 주와 다음 주에 나온 부서를 순서대로 합친다.

    한쪽 주에만 있는 부서도 빠뜨리지 않아야, 아직 쓰지 않은 부서까지 카드로 보인다.
    """
    order, seen = [], {}

    def take(week_like):
        for d in (week_like or {}).get('depts', []):
            nm = (d.get('name') or '').strip()
            if not nm or nm == MAJOR_NAME or nm in seen:
                continue
            seen[nm] = {'name': nm, 'short': d.get('short') or nm}
            order.append(nm)

    take(data.get('thisWeek'))
    take(data.get('nextWeek'))
    if not order:
        for mon in data.get('months', []):
            take(mon)
    return [seen[nm] for nm in order]


# ------------------------------------------------------------------ 입력 현황

def _chips(filled, missing):
    parts = []
    for n in (filled or []):
        parts.append('<span class="wp-chip wp-ok">✓ %s</span>' % _esc(n))
    for n in (missing or []):
        parts.append('<span class="wp-chip wp-bad">%s</span>' % _esc(n))
    return ''.join(parts) or '<span class="wp-muted">부서 정보가 없습니다.</span>'


def _stat(title, obj, empty_msg):
    if not obj:
        return ('<div class="wp-stat"><div class="wp-stat-top">'
                '<span class="wp-stat-title">%s</span></div>'
                '<div class="wp-muted">%s</div></div>' % (_esc(title), _esc(empty_msg)))
    filled = obj.get('filled', [])
    missing = obj.get('missing', [])
    total = len(filled) + len(missing)
    done = len(filled)
    cls = 'wp-done' if (total and done == total) else 'wp-part'
    return ('<div class="wp-stat"><div class="wp-stat-top">'
            '<span class="wp-stat-title">%s</span>'
            '<span class="wp-count %s">%d<i>/%d</i></span></div>'
            '<div class="wp-chips">%s</div></div>'
            % (_esc(title), cls, done, total, _chips(filled, missing)))


# ------------------------------------------------------------------ 주요일정

def _major_row(label, week, today_iso):
    """주요일정 한 줄. 맨 앞 칸에 주 이름을 두고 뒤에 요일 여섯 칸을 붙인다."""
    head = ('<div class="wp-rowhead"><b>%s</b><span>%s</span></div>'
            % (_esc(label), _esc((week or {}).get('range', ''))))
    if not week:
        return head + '<div class="wp-mcell wp-mwide">아직 이 주의 탭이 없습니다.</div>'
    major = _find_dept(week, MAJOR_NAME) or {}
    cells = []
    for i in range(6):
        lines = _lines_of(major, i)
        body = (''.join('<div class="wp-mline">%s</div>' % _esc(x) for x in lines)
                if lines else '<div class="wp-mnone">—</div>')
        cls = 'wp-mcell is-today' if _is_today(week, i, today_iso) else 'wp-mcell'
        cells.append('<div class="%s"><div class="wp-mday">%s</div>%s</div>'
                     % (cls, _esc(_day_label(week, i)), body))
    return head + ''.join(cells)


def _major_block(data, today_iso):
    rows = (_major_row('이번 주', data.get('thisWeek'), today_iso)
            + _major_row('다음 주', data.get('nextWeek'), today_iso))
    return ('<div class="wp-sub">주요일정 <em>학사일정에서 자동으로 옮겨 옵니다</em></div>'
            '<div class="wp-major">%s</div>' % rows)


# ------------------------------------------------------------------ 전달·협의사항

def _notes_block(data):
    items = []
    for label, week in (('이번 주', data.get('thisWeek')), ('다음 주', data.get('nextWeek'))):
        text = ((week or {}).get('notes') or '').strip()
        if text:
            items.append('<div class="wp-note"><b>%s 전달·협의사항</b><div>%s</div></div>'
                         % (_esc(label), _nl2br(text)))
    if not items:
        return ''
    return '<div class="wp-notes">%s</div>' % ''.join(items)


# ------------------------------------------------------------------ 부서별 계획

def _card_week(label, week, dept_name, today_iso):
    groups = []
    dept = _find_dept(week, dept_name)
    if week and dept:
        for i in range(6):
            lines = _lines_of(dept, i)
            if not lines:
                continue
            chip = 'wp-dchip is-today' if _is_today(week, i, today_iso) else 'wp-dchip'
            day = DAY_KO[i] if i < 5 else '주말'
            groups.append('<div class="wp-dgroup"><span class="%s">%s</span>'
                          '<div class="wp-lines">%s</div></div>'
                          % (chip, _esc(day),
                             ''.join('<div>%s</div>' % _esc(x) for x in lines)))
    body = ''.join(groups) or '<div class="wp-cnone">아직 입력하지 않았습니다.</div>'
    return ('<div class="wp-cwk"><span class="wp-clabel">%s</span>'
            '<div class="wp-cbody">%s</div></div>' % (_esc(label), body))


def _dept_card(dept, idx, data, today_iso):
    return ('<div class="wp-card"><h4 style="color:%s">%s</h4>%s%s</div>'
            % (_tone(idx), _esc(dept['short']),
               _card_week('이번 주', data.get('thisWeek'), dept['name'], today_iso),
               _card_week('다음 주', data.get('nextWeek'), dept['name'], today_iso)))


def _cards_block(data, today_iso):
    depts = _dept_index(data)
    if not depts:
        return ('<div class="wp-sub">부서별 계획</div>'
                '<div class="wp-empty">부서 목록을 불러오지 못했습니다.</div>')
    cards = ''.join(_dept_card(d, i, data, today_iso) for i, d in enumerate(depts))
    return ('<div class="wp-sub">부서별 계획 <em>부서마다 이번 주와 다음 주를 함께 봅니다</em></div>'
            '<div class="wp-cards">%s</div>' % cards)


def _ssr(data):
    today = data.get('todayIso', '')
    strip = ['<div class="wp-strip">',
             _stat('이번 주 입력', data.get('thisWeek'), '이번 주 탭이 아직 없습니다.'),
             _stat('다음 주 입력', data.get('nextWeek'), '다음 주 탭이 아직 없습니다.')]
    for mon in data.get('months', []):
        strip.append(_stat('%s 사전 계획' % mon.get('label', ''), mon, ''))
    strip.append('</div>')
    body = ('<div class="wp-main">'
            + _major_block(data, today)
            + _notes_block(data)
            + _cards_block(data, today)
            + '</div>')
    return ''.join(strip) + body


# ------------------------------------------------------------------ 스타일

_CSS = """
<style>
  .hero{margin-top:16px}
  .hero .panel-head{background:#fbfaf7}
  .wp-btn{display:inline-block;font-size:12.5px;font-weight:600;padding:7px 14px;border-radius:9px;
    border:1px solid var(--line);background:#fff;color:var(--text);text-decoration:none;cursor:pointer;
    white-space:nowrap;transition:.14s;font-family:var(--sans)}
  .wp-btn:hover{border-color:var(--ink)}
  .wp-btn.wp-primary{background:var(--ink);border-color:var(--ink);color:#f6f4ef}
  .wp-btn.wp-primary:hover{background:#000}

  .wp-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line-2);
    border-bottom:1px solid var(--line-2)}
  .wp-stat{background:#fff;padding:12px 20px 13px}
  .wp-stat-top{display:flex;align-items:baseline;gap:9px;margin-bottom:9px}
  .wp-stat-title{font-size:12.5px;font-weight:700;color:var(--muted);letter-spacing:.01em}
  .wp-count{font-family:var(--mono);font-size:17px;font-weight:600;line-height:1;margin-left:auto}
  .wp-count i{font-style:normal;font-size:12px;color:var(--faint)}
  .wp-count.wp-done{color:var(--teal)}
  .wp-count.wp-part{color:var(--amber)}
  .wp-chips{display:flex;flex-wrap:wrap;gap:5px}
  .wp-chip{font-size:11.5px;padding:3px 9px;border-radius:20px;font-weight:600;white-space:nowrap}
  .wp-chip.wp-ok{background:var(--teal-bg);color:var(--teal)}
  .wp-chip.wp-bad{background:var(--amber-bg);color:var(--amber);
    border:1px dashed rgba(169,90,8,.35)}
  .wp-muted{color:var(--faint);font-size:12.5px}

  .wp-main{padding:16px 20px 18px}
  .wp-empty{color:var(--faint);font-size:13px;padding:14px 2px}
  .wp-sub{font-size:11.5px;font-weight:700;color:var(--muted);letter-spacing:.01em;
    margin:0 0 8px;display:flex;align-items:baseline;gap:9px}
  .wp-sub::before{content:"";width:3px;height:11px;border-radius:2px;background:var(--line);
    align-self:center}
  .wp-sub em{font-style:normal;font-weight:400;font-size:11.5px;color:#b0a99c}
  .wp-notes + .wp-sub,.wp-major + .wp-sub{margin-top:16px}

  /* 주요일정: 맨 앞 한 칸이 주 이름이고, 그 뒤로 요일 여섯 칸이 이어진다. */
  .wp-major{display:grid;grid-template-columns:112px repeat(6,1fr);gap:6px}
  .wp-rowhead{display:flex;flex-direction:column;justify-content:center;gap:3px;
    padding:7px 10px;border-radius:10px;background:var(--ink);color:#f1eee7}
  .wp-rowhead b{font-size:13px;font-weight:700;letter-spacing:-.01em}
  .wp-rowhead span{font-family:var(--mono);font-size:9.5px;color:#a5b0bc;letter-spacing:.02em}
  .wp-mcell{border:1px solid var(--line);border-radius:10px;padding:7px 9px;background:#fcfbf9;
    min-height:52px}
  .wp-mcell.wp-mwide{grid-column:2/-1;display:flex;align-items:center;color:var(--faint);
    font-size:12.5px}
  .wp-mcell.is-today{background:var(--today-bg);border-color:#c8dbee}
  .wp-mday{font-family:var(--mono);font-size:9.5px;font-weight:600;color:var(--muted);
    letter-spacing:.04em}
  .wp-mcell.is-today .wp-mday{color:var(--today)}
  .wp-mline{font-size:11.5px;line-height:1.4;margin-top:4px;color:#2b3542;word-break:break-word}
  .wp-mnone{font-size:11.5px;color:#d3ccbf;margin-top:4px}

  /* 전달·협의사항 */
  .wp-notes{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
  .wp-note{background:var(--amber-bg);border:1px solid #eddcc2;border-radius:11px;
    padding:9px 12px;font-size:12.5px;line-height:1.55}
  .wp-note b{display:block;margin-bottom:3px;color:var(--amber);font-size:11.5px;letter-spacing:.02em}

  /* 부서별 계획: 부서 한 곳이 카드 한 장이고, 그 안에 두 주가 나란히 들어간다. */
  .wp-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;align-items:stretch}
  .wp-card{border:1px solid var(--line);border-radius:12px;padding:11px 13px 12px;background:#fff;
    display:flex;flex-direction:column;min-width:0}
  .wp-card h4{margin:0 0 8px;font-size:12.5px;font-weight:700;letter-spacing:-.01em}
  .wp-cwk{display:grid;grid-template-columns:46px 1fr;gap:9px;padding:8px 0;
    border-top:1px dotted var(--line)}
  .wp-cwk:first-of-type{border-top:0;padding-top:0}
  .wp-clabel{font-family:var(--mono);font-size:10px;font-weight:600;color:var(--faint);
    letter-spacing:.02em;padding-top:2px}
  .wp-cbody{min-width:0}
  .wp-cnone{font-size:12px;color:#c9c2b5}
  .wp-dgroup{display:grid;grid-template-columns:30px 1fr;gap:7px;padding:2px 0}
  .wp-dchip{font-family:var(--mono);font-size:10px;font-weight:600;color:var(--muted);padding-top:2px}
  .wp-dchip.is-today{color:var(--today)}
  .wp-lines{font-size:12.5px;line-height:1.55;color:#2b3542;word-break:break-word;min-width:0}

  .wp-panel{display:none;border-top:1px solid var(--line-2);background:#fbfaf7;padding:18px 22px 22px}
  .wp-panel.wp-open{display:block}
  .wp-pillrow{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:11px}
  .wp-pill{font-size:12.5px;padding:6px 14px;border-radius:20px;border:1px solid var(--line);
    background:#fff;cursor:pointer;user-select:none;transition:.14s}
  .wp-pill:hover{border-color:var(--ink)}
  .wp-pill.wp-sel{background:var(--ink);border-color:var(--ink);color:#f6f4ef;font-weight:600}
  .wp-formgrid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:12px 0}
  .wp-field label{display:block;font-family:var(--mono);font-size:10.5px;font-weight:600;
    color:var(--muted);margin-bottom:4px;letter-spacing:.04em}
  .wp-field textarea,.wp-note-in{width:100%;min-height:96px;border:1px solid var(--line);
    border-radius:10px;padding:9px 11px;font-family:var(--sans);font-size:13px;line-height:1.6;
    resize:vertical;color:var(--text);background:#fff}
  .wp-field textarea:focus,.wp-note-in:focus{outline:0;border-color:var(--ink);
    box-shadow:0 0 0 3px rgba(19,27,36,.06)}
  .wp-actions{display:flex;align-items:center;gap:12px;margin-top:12px}
  .wp-foot{padding:10px 22px 14px;font-family:var(--mono);font-size:10.5px;color:var(--faint);
    border-top:1px solid var(--line-2);letter-spacing:.03em}

  .wp-toast{position:fixed;left:50%;bottom:30px;transform:translateX(-50%);background:var(--ink);
    color:#f6f4ef;font-size:13.5px;padding:12px 22px;border-radius:12px;opacity:0;
    pointer-events:none;transition:opacity .25s;z-index:9999;max-width:88%;text-align:center;
    box-shadow:0 12px 34px rgba(19,27,36,.28)}
  .wp-toast.wp-show{opacity:1}

  @media (max-width:1500px){.wp-cards{grid-template-columns:repeat(3,1fr)}}
  @media (max-width:1400px){
    .wp-strip{grid-template-columns:repeat(2,1fr)}
    .wp-formgrid{grid-template-columns:repeat(3,1fr)}
  }
  @media (max-width:1180px){.wp-cards{grid-template-columns:repeat(2,1fr)}}
  @media (max-width:1100px){
    .wp-major{grid-template-columns:repeat(3,1fr)}
    .wp-rowhead{grid-column:1/-1;flex-direction:row;align-items:baseline;gap:9px}
    .wp-mcell.wp-mwide{grid-column:1/-1}
    .wp-notes{grid-template-columns:1fr}
  }
  @media (max-width:760px){
    .wp-strip{grid-template-columns:1fr}
    .wp-formgrid{grid-template-columns:repeat(2,1fr)}
    .wp-cards{grid-template-columns:1fr}
  }
</style>
"""


# ------------------------------------------------------------------ 브라우저 스크립트

_JS = r"""
<script>
(function(){
  var API="__API_URL__";
  var DATA=__DATA_JSON__;
  var TONES=["#a95a08","#0e6f61","#3f5fa8","#8a3b62","#4a6b23","#7a4a1f"];
  var MAJOR='주요일정';
  var st={week:'next',dept:null,busy:false,pin:''};
  var DAY_KO=['월','화','수','목','금','토~일'];

  function esc(s){var d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}
  function nl2br(s){return esc(s).replace(/\n/g,'<br>');}
  function md(iso){var p=String(iso).split('-');return (+p[1])+'/'+(+p[2]);}
  function dayLabel(w,i){return i<5?DAY_KO[i]+' '+md(w.dates[i]):'토~일 '+md(w.dates[5])+'~'+md(w.dates[6]);}
  function byId(id){return document.getElementById(id);}
  function tone(i){return TONES[i%TONES.length];}

  function isToday(w,i,today){
    var d=(w&&w.dates)||[];
    if(!d.length)return false;
    return i<5?d[i]===today:(today===d[5]||today===d[6]);
  }
  function linesOf(dept,i){
    var t=(((dept||{}).days||[])[i]||'').trim();
    if(!t)return [];
    return t.split(/\n/).map(function(x){return x.trim();}).filter(Boolean);
  }
  function findDept(w,name){
    var out=null;
    ((w||{}).depts||[]).forEach(function(d){if((d.name||'').trim()===name)out=d;});
    return out;
  }
  function deptIndex(){
    var order=[],seen={};
    function take(w){
      ((w||{}).depts||[]).forEach(function(d){
        var nm=(d.name||'').trim();
        if(!nm||nm===MAJOR||seen[nm])return;
        seen[nm]={name:nm,short:d.short||nm};order.push(nm);
      });
    }
    take(DATA.thisWeek);take(DATA.nextWeek);
    if(!order.length)(DATA.months||[]).forEach(take);
    return order.map(function(nm){return seen[nm];});
  }

  function chips(f,m){
    var h='';
    (f||[]).forEach(function(n){h+='<span class="wp-chip wp-ok">✓ '+esc(n)+'</span>';});
    (m||[]).forEach(function(n){h+='<span class="wp-chip wp-bad">'+esc(n)+'</span>';});
    return h||'<span class="wp-muted">부서 정보가 없습니다.</span>';
  }
  function stat(title,o,emptyMsg){
    if(!o)return '<div class="wp-stat"><div class="wp-stat-top"><span class="wp-stat-title">'+esc(title)
      +'</span></div><div class="wp-muted">'+esc(emptyMsg)+'</div></div>';
    var total=(o.filled||[]).length+(o.missing||[]).length,done=(o.filled||[]).length;
    return '<div class="wp-stat"><div class="wp-stat-top"><span class="wp-stat-title">'+esc(title)+'</span>'
      +'<span class="wp-count '+((total&&done===total)?'wp-done':'wp-part')+'">'+done+'<i>/'+total+'</i></span></div>'
      +'<div class="wp-chips">'+chips(o.filled,o.missing)+'</div></div>';
  }

  function majorRow(label,w,today){
    var head='<div class="wp-rowhead"><b>'+esc(label)+'</b><span>'+esc((w||{}).range||'')+'</span></div>';
    if(!w)return head+'<div class="wp-mcell wp-mwide">아직 이 주의 탭이 없습니다.</div>';
    var major=findDept(w,MAJOR)||{},cells='';
    for(var i=0;i<6;i++){
      var ls=linesOf(major,i),body='';
      if(ls.length){ls.forEach(function(x){body+='<div class="wp-mline">'+esc(x)+'</div>';});}
      else{body='<div class="wp-mnone">—</div>';}
      cells+='<div class="'+(isToday(w,i,today)?'wp-mcell is-today':'wp-mcell')+'">'
        +'<div class="wp-mday">'+esc(dayLabel(w,i))+'</div>'+body+'</div>';
    }
    return head+cells;
  }
  function majorBlock(d,today){
    return '<div class="wp-sub">주요일정 <em>학사일정에서 자동으로 옮겨 옵니다</em></div>'
      +'<div class="wp-major">'+majorRow('이번 주',d.thisWeek,today)
      +majorRow('다음 주',d.nextWeek,today)+'</div>';
  }
  function notesBlock(d){
    var items='';
    [['이번 주',d.thisWeek],['다음 주',d.nextWeek]].forEach(function(p){
      var t=((p[1]||{}).notes||'').trim();
      if(t)items+='<div class="wp-note"><b>'+esc(p[0])+' 전달·협의사항</b><div>'+nl2br(t)+'</div></div>';
    });
    return items?('<div class="wp-notes">'+items+'</div>'):'';
  }
  function cardWeek(label,w,name,today){
    var groups='',dept=findDept(w,name);
    if(w&&dept){
      for(var i=0;i<6;i++){
        var ls=linesOf(dept,i);
        if(!ls.length)continue;
        var body='';
        ls.forEach(function(x){body+='<div>'+esc(x)+'</div>';});
        groups+='<div class="wp-dgroup"><span class="'+(isToday(w,i,today)?'wp-dchip is-today':'wp-dchip')+'">'
          +esc(i<5?DAY_KO[i]:'주말')+'</span><div class="wp-lines">'+body+'</div></div>';
      }
    }
    if(!groups)groups='<div class="wp-cnone">아직 입력하지 않았습니다.</div>';
    return '<div class="wp-cwk"><span class="wp-clabel">'+esc(label)+'</span>'
      +'<div class="wp-cbody">'+groups+'</div></div>';
  }
  function cardsBlock(d,today){
    var depts=deptIndex();
    if(!depts.length)return '<div class="wp-sub">부서별 계획</div>'
      +'<div class="wp-empty">부서 목록을 불러오지 못했습니다.</div>';
    var cards='';
    depts.forEach(function(dp,i){
      cards+='<div class="wp-card"><h4 style="color:'+tone(i)+'">'+esc(dp.short)+'</h4>'
        +cardWeek('이번 주',d.thisWeek,dp.name,today)
        +cardWeek('다음 주',d.nextWeek,dp.name,today)+'</div>';
    });
    return '<div class="wp-sub">부서별 계획 <em>부서마다 이번 주와 다음 주를 함께 봅니다</em></div>'
      +'<div class="wp-cards">'+cards+'</div>';
  }
  function renderAll(){
    var d=DATA,today=d.todayIso||'';
    var h='<div class="wp-strip">';
    h+=stat('이번 주 입력',d.thisWeek,'이번 주 탭이 아직 없습니다.');
    h+=stat('다음 주 입력',d.nextWeek,'다음 주 탭이 아직 없습니다.');
    (d.months||[]).forEach(function(m){h+=stat(m.label+' 사전 계획',m,'');});
    h+='</div><div class="wp-main">'+majorBlock(d,today)+notesBlock(d)+cardsBlock(d,today)+'</div>';
    var c=byId('wpContent'); if(c)c.innerHTML=h;
    var b=byId('wpCount');
    if(b&&d.nextWeek){
      var t=(d.nextWeek.filled||[]).length+(d.nextWeek.missing||[]).length;
      b.textContent='다음 주 '+(d.nextWeek.filled||[]).length+'/'+t+' 부서';
    }
    renderInput();
  }
  function toast(msg){
    var t=byId('wpToast'); if(!t)return;
    t.textContent=msg;t.className='wp-toast wp-show';
    clearTimeout(t._h);t._h=setTimeout(function(){t.className='wp-toast';},3400);
  }
  function reveal(){
    var bi=byId('wpBtnInput'),br=byId('wpBtnRefresh');
    if(bi&&bi.style.display!==''){bi.style.display='';bi.onclick=togglePanel;}
    if(br&&br.style.display!==''){br.style.display='';br.onclick=function(){refresh(true);};}
  }
  function refresh(manual){
    if(!API)return;
    fetch(API+'?api=dashboard').then(function(r){return r.json();}).then(function(j){
      if(j&&j.thisWeek!==undefined){
        DATA=j;reveal();renderAll();
        var s=byId('wpStamp');
        if(s)s.textContent='실시간 자료 · '+new Date().toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'})+' 기준';
        if(manual)toast('최신 내용으로 갱신했습니다.');
      }else if(manual){toast('갱신에 실패했습니다.');}
    }).catch(function(){if(manual)toast('네트워크 연결을 확인해 주세요.');});
  }

  function weekObj(which){return which==='this'?DATA.thisWeek:DATA.nextWeek;}
  function togglePanel(){
    var p=byId('wpPanel'); if(!p)return;
    var open=p.className.indexOf('wp-open')>=0;
    p.className='wp-panel'+(open?'':' wp-open');
    if(!open){renderInput();p.scrollIntoView({behavior:'smooth',block:'nearest'});}
  }
  function renderInput(){
    var box=byId('wpPanelBody'),p=byId('wpPanel');
    if(!box||!p||p.className.indexOf('wp-open')<0)return;
    var depts=deptIndex();
    if(!depts.length){box.innerHTML='<div class="wp-muted">부서 목록을 불러오지 못했습니다. 시트에서 입력해 주세요.</div>';return;}
    var h='<div class="wp-pillrow">'
      +'<span class="wp-pill'+(st.week==='this'?' wp-sel':'')+'" data-wk="this">이번 주'+(DATA.thisWeek?' ('+esc(DATA.thisWeek.label)+')':'')+'</span>'
      +'<span class="wp-pill'+(st.week==='next'?' wp-sel':'')+'" data-wk="next">다음 주'+(DATA.nextWeek?' ('+esc(DATA.nextWeek.label)+')':'')+'</span>'
      +'</div><div class="wp-pillrow">';
    depts.forEach(function(d,i){
      h+='<span class="wp-pill'+(st.dept===d.name?' wp-sel':'')+'" data-dept="'+i+'">'+esc(d.short)+'</span>';
    });
    h+='</div>';
    if(st.dept){
      var w=weekObj(st.week),mine=findDept(w,st.dept);
      var days=(mine&&mine.days)?mine.days:['','','','','',''];
      h+='<div class="wp-formgrid">';
      for(var i=0;i<6;i++){
        h+='<div class="wp-field"><label>'+esc(w?dayLabel(w,i):DAY_KO[i])+'</label>'
          +'<textarea id="wpDay'+i+'">'+esc(days[i]||'')+'</textarea></div>';
      }
      h+='</div><div class="wp-field"><label>전달·협의사항 (부서 공통)</label>'
        +'<textarea class="wp-note-in" id="wpNote">'+esc(w?(w.notes||''):'')+'</textarea></div>';
      if(DATA.pinRequired){
        h+='<div class="wp-field" style="max-width:240px;margin-top:10px"><label>입력 비밀번호</label>'
          +'<textarea id="wpPin" style="min-height:40px">'+esc(st.pin)+'</textarea></div>';
      }
      h+='<div class="wp-actions"><span class="wp-btn wp-primary" id="wpSave">저장</span>'
        +'<span class="wp-muted">저장하면 시트에 기록되고 노션에는 10분 안에 반영됩니다.</span></div>';
    }else{
      h+='<div class="wp-muted">주와 부서를 고르면 입력 칸이 열립니다.</div>';
    }
    box.innerHTML=h;
    box.querySelectorAll('[data-wk]').forEach(function(el){
      el.onclick=function(){st.week=el.getAttribute('data-wk');renderInput();};
    });
    box.querySelectorAll('[data-dept]').forEach(function(el){
      el.onclick=function(){st.dept=deptIndex()[+el.getAttribute('data-dept')].name;renderInput();};
    });
    var sv=byId('wpSave'); if(sv)sv.onclick=saveAll;
  }
  function post(body){
    if(DATA.pinRequired){var pe=byId('wpPin');if(pe)st.pin=pe.value;body.pin=st.pin;}
    return fetch(API,{method:'POST',body:JSON.stringify(body)}).then(function(r){return r.json();});
  }
  function saveAll(){
    if(st.busy)return;
    var w=weekObj(st.week),mine=findDept(w,st.dept);
    var jobs=[];
    for(var i=0;i<6;i++){
      var el=byId('wpDay'+i); if(!el)continue;
      var old=mine?((mine.days||[])[i]||''):'';
      if(el.value!==old)jobs.push({action:'save',week:st.week,dept:st.dept,day:i,text:el.value});
    }
    var ne=byId('wpNote');
    if(ne&&ne.value!==(w?(w.notes||''):''))jobs.push({action:'saveNote',week:st.week,text:ne.value});
    if(!jobs.length){toast('바뀐 내용이 없습니다.');return;}
    st.busy=true;toast('저장 중입니다. ('+jobs.length+'건)');
    var idx=0,last=null,failed=null;
    (function next(){
      if(idx>=jobs.length){
        st.busy=false;
        if(last){DATA=last;renderAll();}else{refresh(false);}
        toast(failed?('일부 저장에 실패했습니다: '+failed):'저장되었습니다. 노션에는 10분 안에 반영됩니다.');
        return;
      }
      post(jobs[idx]).then(function(j){
        if(!j.ok)failed=j.error||'오류';
        if(j.data)last=j.data;
        idx++;next();
      }).catch(function(){failed='네트워크 오류';idx++;next();});
    })();
  }

  /* API 호출이 실제로 성공한 뒤에야 입력·새로 고침 단추를 보여 준다.
     프로그램이 파일을 그대로 여는 환경에서는 호출이 막힐 수 있는데,
     그때에는 미리 그려 둔 내용과 시트 링크만 남으므로 혼선이 없다. */
  function init(){
    if(!API||!window.fetch)return;
    refresh(false);
    setInterval(function(){refresh(false);},5*60*1000);
  }
  /* 문서를 이미 다 불러온 뒤에 이 스크립트가 실행되는 경우에도 동작해야 한다. */
  if(document.readyState==='loading'){window.addEventListener('DOMContentLoaded',init);}
  else{init();}
})();
</script>
"""


# ------------------------------------------------------------------ 조립

def _fetch(api_url, timeout):
    url = api_url + ('&' if '?' in api_url else '?') + 'api=dashboard'
    r = requests.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    data = r.json()
    if not data.get('ok'):
        raise RuntimeError('API 응답 오류: %s' % data.get('error'))
    return data


def build_section(api_url=None, timeout=45):
    """대시보드의 주 영역이 되는 '주간 업무 계획' 구역을 돌려준다.

    주소가 없거나 조회에 실패하면 빈 문자열을 돌려주므로 브리핑 발행은 그대로 진행된다.
    """
    api_url = (api_url or os.environ.get('WORKPLAN_API_URL') or '').strip()
    if not api_url:
        print('  [업무계획] WORKPLAN_API_URL 이 없어 구역을 넣지 않습니다.')
        return ''
    try:
        data = _fetch(api_url, timeout)
    except Exception as e:
        print('  [업무계획] 조회 실패로 구역을 넣지 않습니다: %s' % e)
        return ''

    nw = data.get('nextWeek') or {}
    done = len(nw.get('filled', []))
    total = done + len(nw.get('missing', []))
    count_label = ('다음 주 %d/%d 부서' % (done, total)) if nw else '자료 없음'

    links = ['<span class="wp-btn wp-primary" id="wpBtnInput" style="display:none">여기서 바로 입력</span>',
             '<span class="wp-btn" id="wpBtnRefresh" style="display:none">새로 고침</span>']
    if data.get('sheetUrl'):
        links.append('<a class="wp-btn" href="%s" target="_blank" rel="noopener">시트</a>'
                     % _esc(data['sheetUrl']))
    if data.get('notionDbUrl'):
        links.append('<a class="wp-btn" href="%s" target="_blank" rel="noopener">노션</a>'
                     % _esc(data['notionDbUrl']))

    body = (
        '<section class="panel hero">'
        '<div class="panel-head">'
        '<h2>주간 업무 계획</h2>'
        '<span class="sub">부서별 주간 계획 · 시트와 노션에 함께 반영됩니다</span>'
        '<span class="sp"></span>'
        f'<span class="tag" id="wpCount">{_esc(count_label)}</span>'
        f'{"".join(links)}'
        '</div>'
        f'<div id="wpContent">{_ssr(data)}</div>'
        '<div class="wp-panel" id="wpPanel"><div id="wpPanelBody"></div></div>'
        '<div class="wp-foot" id="wpStamp">발행 시각 기준 자료입니다. 입력은 [시트]를 눌러 주세요.</div>'
        '</section>'
        '<div class="wp-toast" id="wpToast"></div>'
    )

    script = (_JS
              .replace('__API_URL__', api_url.replace('\\', '\\\\').replace('"', '\\"'))
              .replace('__DATA_JSON__', json.dumps(data, ensure_ascii=False)))
    print('  [업무계획] 구역을 넣었습니다. (%s)' % count_label)
    return _CSS + body + script
