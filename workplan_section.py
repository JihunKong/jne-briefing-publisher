# -*- coding: utf-8 -*-
"""
briefing.html 안에 '주간 업무 계획' 구역을 끼워 넣는 모듈.

각 선생님 PC의 학사일정브리핑.exe는 gist의 briefing.html만 내려받아 표시하므로,
주간 업무 계획도 이 파일 안에 함께 실려 있어야 선생님들이 볼 수 있습니다.

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


# ------------------------------------------------------------------ 조각 그리기

def _chips(filled, missing):
    parts = []
    for n in (filled or []):
        parts.append('<span class="wp-chip wp-ok">✓ %s</span>' % _esc(n))
    for n in (missing or []):
        parts.append('<span class="wp-chip wp-bad">%s 미입력</span>' % _esc(n))
    return ''.join(parts) or '<span class="wp-muted">부서 정보가 없습니다.</span>'


def _stat(title, obj, empty_msg):
    if not obj:
        return ('<div class="wp-stat"><div class="wp-stat-title">%s</div>'
                '<div class="wp-muted">%s</div></div>' % (_esc(title), _esc(empty_msg)))
    filled = obj.get('filled', [])
    missing = obj.get('missing', [])
    total = len(filled) + len(missing)
    done = len(filled)
    cls = 'wp-done' if (total and done == total) else 'wp-part'
    return ('<div class="wp-stat"><div class="wp-stat-title">%s '
            '<span class="wp-count %s">%d/%d 부서</span></div>'
            '<div class="wp-chips">%s</div></div>'
            % (_esc(title), cls, done, total, _chips(filled, missing)))


def _week_items(week, today_iso):
    rows = []
    for i in range(6):
        items = []
        for dept in week.get('depts', []):
            days = dept.get('days', [])
            text = (days[i] or '').strip() if i < len(days) else ''
            if not text:
                continue
            for line in [ln.strip() for ln in text.split('\n') if ln.strip()]:
                items.append('<li><b>%s</b> · %s</li>' % (_esc(dept.get('short', '')), _esc(line)))
        if not items:
            continue
        dates = week.get('dates', [])
        is_today = ((i < 5 and dates[i] == today_iso)
                    or (i == 5 and today_iso in (dates[5], dates[6])))
        is_past = i < 5 and dates[i] < today_iso and not is_today
        cls = 'wp-day' + (' wp-today' if is_today else '') + (' wp-past' if is_past else '')
        badge = '<span class="wp-today-badge">오늘</span>' if is_today else ''
        rows.append('<div class="%s"><div class="wp-day-name">%s%s</div><ul>%s</ul></div>'
                    % (cls, _esc(_day_label(week, i)), badge, ''.join(items)))
    if not rows:
        return '<div class="wp-muted">아직 입력된 내용이 없습니다.</div>'
    return ''.join(rows)


def _week_block(title, week, today_iso):
    if not week:
        return ('<div class="wp-block"><div class="wp-block-head">%s</div>'
                '<div class="wp-muted">아직 이 주의 탭이 없습니다.</div></div>' % _esc(title))
    notes = ''
    if (week.get('notes') or '').strip():
        notes = ('<div class="wp-notes"><b>📣 전달·협의사항</b><div>%s</div></div>'
                 % _nl2br(week['notes']))
    return ('<div class="wp-block"><div class="wp-block-head">%s '
            '<small>%s · %s</small></div>%s%s</div>'
            % (_esc(title), _esc(week.get('label', '')), _esc(week.get('range', '')),
               notes, _week_items(week, today_iso)))


def _ssr(data):
    today = data.get('todayIso', '')
    out = ['<div class="wp-stats">']
    out.append(_stat('이번 주 입력 현황', data.get('thisWeek'), '이번 주 탭이 아직 없습니다.'))
    out.append(_stat('다음 주 입력 현황', data.get('nextWeek'), '다음 주 탭이 아직 없습니다.'))
    for mon in data.get('months', []):
        out.append(_stat('%s 월간 사전 계획' % mon.get('label', ''), mon, ''))
    out.append('</div>')
    out.append(_week_block('📌 이번 주 할 일', data.get('thisWeek'), today))
    out.append(_week_block('⏭️ 다음 주 할 일', data.get('nextWeek'), today))
    return ''.join(out)


# ------------------------------------------------------------------ 스타일

_CSS = """
<style>
  .wp-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin-bottom:14px}
  .wp-stat{border:1px solid #e1e8ed;border-radius:10px;padding:12px 14px;background:#fafbfc}
  .wp-stat-title{font-size:13px;font-weight:700;color:#5d6d7e;margin-bottom:8px}
  .wp-count{font-size:11px;font-weight:700;padding:2px 8px;border-radius:9px;margin-left:4px}
  .wp-count.wp-done{background:#d5f5e3;color:#1e8449}
  .wp-count.wp-part{background:#fdebd0;color:#b9770e}
  .wp-chips{display:flex;flex-wrap:wrap;gap:5px}
  .wp-chip{font-size:12px;padding:3px 9px;border-radius:9px;font-weight:600;white-space:nowrap}
  .wp-chip.wp-ok{background:#eafaf1;color:#1e8449;border:1px solid #a9dfbf}
  .wp-chip.wp-bad{background:#fdedec;color:#c0392b;border:1px solid #f5b7b1}
  .wp-muted{color:#95a5a6;font-size:13px}
  .wp-block{border:1px solid #e1e8ed;border-radius:10px;padding:12px 14px;margin-bottom:10px}
  .wp-block-head{font-size:15px;font-weight:700;margin-bottom:8px;color:#2c3e50}
  .wp-block-head small{font-weight:500;color:#7f8c8d;font-size:12px;margin-left:4px}
  .wp-notes{background:#fef9e7;border:1px solid #f7dc6f;border-radius:8px;padding:9px 12px;margin-bottom:10px;font-size:13px}
  .wp-notes b{display:block;margin-bottom:3px;color:#9a7d0a}
  .wp-day{padding:7px 0;border-top:1px dashed #ecf0f1}
  .wp-day:first-of-type{border-top:0}
  .wp-day-name{font-size:12px;font-weight:700;color:#7f8c8d;margin-bottom:3px}
  .wp-day.wp-today{background:#eef2fb;border-radius:8px;padding:8px 10px;border-top:0}
  .wp-day.wp-today .wp-day-name{color:#4054b2}
  .wp-day.wp-past{opacity:.5}
  .wp-today-badge{background:#667eea;color:#fff;font-size:10px;padding:1px 7px;border-radius:8px;margin-left:6px;vertical-align:middle}
  .wp-day ul{margin:0;padding-left:18px;font-size:13.5px;line-height:1.75;color:#34495e}
  .wp-day li b{color:#2c3e50}
  .wp-links{margin-top:12px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  .wp-btn{display:inline-block;font-size:13px;font-weight:600;padding:7px 14px;border-radius:9px;
          border:1px solid #d5dbe3;background:#fff;color:#34495e;text-decoration:none;cursor:pointer}
  .wp-btn:hover{border-color:#667eea;color:#4054b2}
  .wp-btn.wp-primary{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:0}
  .wp-panel{display:none;margin-top:14px;border:1px solid #d6dbe6;border-radius:12px;padding:14px;background:#fbfcfe}
  .wp-panel.wp-open{display:block}
  .wp-pillrow{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
  .wp-pill{font-size:12.5px;padding:5px 12px;border-radius:14px;border:1px solid #d5dbe3;background:#fff;cursor:pointer;user-select:none}
  .wp-pill.wp-sel{background:#667eea;border-color:#667eea;color:#fff;font-weight:600}
  .wp-formgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:9px;margin:10px 0}
  .wp-field label{display:block;font-size:11.5px;font-weight:700;color:#7f8c8d;margin-bottom:3px}
  .wp-field textarea,.wp-note-in{width:100%;min-height:74px;border:1px solid #d5dbe3;border-radius:8px;
          padding:7px 9px;font-family:inherit;font-size:13px;line-height:1.6;resize:vertical;color:#2c3e50}
  .wp-field textarea:focus,.wp-note-in:focus{outline:0;border-color:#667eea}
  .wp-toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:#2c3e50;color:#fff;
          font-size:13.5px;padding:11px 20px;border-radius:11px;opacity:0;pointer-events:none;
          transition:opacity .25s;z-index:9999;max-width:88%;text-align:center}
  .wp-toast.wp-show{opacity:.96}
</style>
"""


# ------------------------------------------------------------------ 브라우저 스크립트

_JS = r"""
<script>
(function(){
  var API="__API_URL__";
  var DATA=__DATA_JSON__;
  var st={week:'next',dept:null,busy:false,pin:''};
  var DAY_KO=['월','화','수','목','금','토~일'];

  function esc(s){var d=document.createElement('div');d.textContent=(s==null?'':String(s));return d.innerHTML;}
  function nl2br(s){return esc(s).replace(/\n/g,'<br>');}
  function md(iso){var p=String(iso).split('-');return (+p[1])+'/'+(+p[2]);}
  function dayLabel(w,i){return i<5?DAY_KO[i]+' '+md(w.dates[i]):'토~일 '+md(w.dates[5])+'~'+md(w.dates[6]);}
  function byId(id){return document.getElementById(id);}

  function chips(f,m){
    var h='';
    (f||[]).forEach(function(n){h+='<span class="wp-chip wp-ok">✓ '+esc(n)+'</span>';});
    (m||[]).forEach(function(n){h+='<span class="wp-chip wp-bad">'+esc(n)+' 미입력</span>';});
    return h||'<span class="wp-muted">부서 정보가 없습니다.</span>';
  }
  function stat(title,o,emptyMsg){
    if(!o)return '<div class="wp-stat"><div class="wp-stat-title">'+esc(title)+'</div><div class="wp-muted">'+esc(emptyMsg)+'</div></div>';
    var total=(o.filled||[]).length+(o.missing||[]).length,done=(o.filled||[]).length;
    return '<div class="wp-stat"><div class="wp-stat-title">'+esc(title)+' <span class="wp-count '
      +((total&&done===total)?'wp-done':'wp-part')+'">'+done+'/'+total+' 부서</span></div>'
      +'<div class="wp-chips">'+chips(o.filled,o.missing)+'</div></div>';
  }
  function weekItems(w,today){
    var out='';
    for(var i=0;i<6;i++){
      var items='';
      (w.depts||[]).forEach(function(d){
        var t=((d.days||[])[i]||'').trim();
        if(!t)return;
        t.split(/\n/).forEach(function(line){
          line=line.trim(); if(!line)return;
          items+='<li><b>'+esc(d.short)+'</b> · '+esc(line)+'</li>';
        });
      });
      if(!items)continue;
      var isToday=(i<5&&w.dates[i]===today)||(i===5&&(today===w.dates[5]||today===w.dates[6]));
      var isPast=i<5&&w.dates[i]<today&&!isToday;
      out+='<div class="wp-day'+(isToday?' wp-today':'')+(isPast?' wp-past':'')+'">'
        +'<div class="wp-day-name">'+esc(dayLabel(w,i))+(isToday?'<span class="wp-today-badge">오늘</span>':'')
        +'</div><ul>'+items+'</ul></div>';
    }
    return out||'<div class="wp-muted">아직 입력된 내용이 없습니다.</div>';
  }
  function weekBlock(title,w,today){
    if(!w)return '<div class="wp-block"><div class="wp-block-head">'+esc(title)+'</div><div class="wp-muted">아직 이 주의 탭이 없습니다.</div></div>';
    var notes=(w.notes||'').trim()?'<div class="wp-notes"><b>📣 전달·협의사항</b><div>'+nl2br(w.notes)+'</div></div>':'';
    return '<div class="wp-block"><div class="wp-block-head">'+esc(title)+' <small>'+esc(w.label)+' · '+esc(w.range)+'</small></div>'
      +notes+weekItems(w,today)+'</div>';
  }
  function renderAll(){
    var d=DATA,today=d.todayIso||'';
    var h='<div class="wp-stats">';
    h+=stat('이번 주 입력 현황',d.thisWeek,'이번 주 탭이 아직 없습니다.');
    h+=stat('다음 주 입력 현황',d.nextWeek,'다음 주 탭이 아직 없습니다.');
    (d.months||[]).forEach(function(m){h+=stat(m.label+' 월간 사전 계획',m,'');});
    h+='</div>'+weekBlock('📌 이번 주 할 일',d.thisWeek,today)+weekBlock('⏭️ 다음 주 할 일',d.nextWeek,today);
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
        if(s)s.textContent='실시간 자료 ('+new Date().toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'})+' 기준)';
        if(manual)toast('최신 내용으로 갱신했습니다.');
      }else if(manual){toast('갱신에 실패했습니다.');}
    }).catch(function(){if(manual)toast('네트워크 연결을 확인해 주세요.');});
  }

  function weekObj(which){return which==='this'?DATA.thisWeek:DATA.nextWeek;}
  function deptSource(){
    var w=weekObj(st.week)||weekObj(st.week==='this'?'next':'this');
    if(w&&w.depts&&w.depts.length)return w.depts;
    if(DATA.months&&DATA.months.length&&DATA.months[0].depts.length)return DATA.months[0].depts;
    return [];
  }
  function togglePanel(){
    var p=byId('wpPanel'); if(!p)return;
    var open=p.className.indexOf('wp-open')>=0;
    p.className='wp-panel'+(open?'':' wp-open');
    if(!open)renderInput();
  }
  function renderInput(){
    var box=byId('wpPanelBody'),p=byId('wpPanel');
    if(!box||!p||p.className.indexOf('wp-open')<0)return;
    var depts=deptSource();
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
      var w=weekObj(st.week),mine=null;
      depts.forEach(function(d){if(d.name===st.dept)mine=d;});
      if(w)(w.depts||[]).forEach(function(d){if(d.name===st.dept)mine=d;});
      var days=(w&&mine&&mine.days)?mine.days:['','','','','',''];
      h+='<div class="wp-formgrid">';
      for(var i=0;i<6;i++){
        h+='<div class="wp-field"><label>'+esc(w?dayLabel(w,i):DAY_KO[i])+'</label>'
          +'<textarea id="wpDay'+i+'">'+esc(days[i]||'')+'</textarea></div>';
      }
      h+='</div><div class="wp-field"><label>전달·협의사항 (부서 공통)</label>'
        +'<textarea class="wp-note-in" id="wpNote">'+esc(w?(w.notes||''):'')+'</textarea></div>';
      if(DATA.pinRequired){
        h+='<div class="wp-field" style="max-width:220px"><label>입력 비밀번호</label>'
          +'<textarea id="wpPin" style="min-height:38px">'+esc(st.pin)+'</textarea></div>';
      }
      h+='<div class="wp-links"><span class="wp-btn wp-primary" id="wpSave">저장</span>'
        +'<span class="wp-muted">저장하면 시트에 기록되고 노션에는 10분 안에 반영됩니다.</span></div>';
    }else{
      h+='<div class="wp-muted">주와 부서를 고르면 입력 칸이 열립니다.</div>';
    }
    box.innerHTML=h;
    box.querySelectorAll('[data-wk]').forEach(function(el){
      el.onclick=function(){st.week=el.getAttribute('data-wk');renderInput();};
    });
    box.querySelectorAll('[data-dept]').forEach(function(el){
      el.onclick=function(){st.dept=deptSource()[+el.getAttribute('data-dept')].name;renderInput();};
    });
    var sv=byId('wpSave'); if(sv)sv.onclick=saveAll;
  }
  function post(body){
    if(DATA.pinRequired){var pe=byId('wpPin');if(pe)st.pin=pe.value;body.pin=st.pin;}
    return fetch(API,{method:'POST',body:JSON.stringify(body)}).then(function(r){return r.json();});
  }
  function saveAll(){
    if(st.busy)return;
    var w=weekObj(st.week),mine=null;
    if(w)(w.depts||[]).forEach(function(d){if(d.name===st.dept)mine=d;});
    var jobs=[];
    for(var i=0;i<6;i++){
      var el=byId('wpDay'+i); if(!el)continue;
      var old=(w&&mine)?((mine.days||[])[i]||''):'';
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

  window.addEventListener('DOMContentLoaded',function(){
    /* API 호출이 실제로 성공한 뒤에야 입력·새로 고침 단추를 보여 준다.
       프로그램이 파일을 그대로 여는 환경에서는 호출이 막힐 수 있는데,
       그때에는 미리 그려 둔 내용과 시트 링크만 남으므로 혼선이 없다. */
    if(!API||!window.fetch)return;
    refresh(false);
    setInterval(function(){refresh(false);},5*60*1000);
  });
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
    """briefing.html 본문에 끼워 넣을 '주간 업무 계획' 구역을 돌려준다.

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

    links = ['<span class="wp-btn wp-primary" id="wpBtnInput" style="display:none">✏️ 여기서 바로 입력</span>',
             '<span class="wp-btn" id="wpBtnRefresh" style="display:none">↻ 새로 고침</span>']
    if data.get('sheetUrl'):
        links.append('<a class="wp-btn" href="%s" target="_blank" rel="noopener">📄 시트에서 입력</a>'
                     % _esc(data['sheetUrl']))
    if data.get('notionDbUrl'):
        links.append('<a class="wp-btn" href="%s" target="_blank" rel="noopener">🗂️ 노션에서 보기</a>'
                     % _esc(data['notionDbUrl']))

    body = (
        '<section>'
        '<h2 style="border-color:#764ba2;">'
        '<span class="icon" style="background:#764ba2;">📋</span>'
        '주간 업무 계획<span class="count" id="wpCount">%s</span></h2>'
        '<div id="wpContent">%s</div>'
        '<div class="wp-links">%s</div>'
        '<div class="wp-panel" id="wpPanel"><div id="wpPanelBody"></div></div>'
        '<div class="wp-muted" style="margin-top:10px;font-size:11.5px" id="wpStamp">'
        '발행 시각 기준 자료입니다. 입력은 아래 [📄 시트에서 입력]을 눌러 주세요.</div>'
        '</section>'
        '<div class="wp-toast" id="wpToast"></div>'
        % (_esc(count_label), _ssr(data), ''.join(links))
    )

    script = (_JS
              .replace('__API_URL__', api_url.replace('\\', '\\\\').replace('"', '\\"'))
              .replace('__DATA_JSON__', json.dumps(data, ensure_ascii=False)))
    print('  [업무계획] 구역을 넣었습니다. (%s)' % count_label)
    return _CSS + body + script
