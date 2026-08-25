"""
학사일정 캐시 발행자 — GitHub Actions에서 매일 자동 실행.

노션 학사일정 + NEIS 시간표 + NEIS 급식 → HTML(+JSON) 생성 → GitHub gist에 PATCH.
다른 선생님들의 학사일정브리핑.exe는 이 gist의 briefing.html을 받아 그대로 표시.

secrets는 환경변수로만 받음 (GitHub Actions Secrets). 코드/repo에 토큰 없음.
"""
import os, sys, json, datetime, traceback, html
import requests, certifi
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    # 주간 업무 계획 구역(같은 폴더의 workplan_section.py). 없으면 브리핑만 발행한다.
    from workplan_section import build_section as build_workplan_section
except Exception:
    def build_workplan_section(*args, **kwargs):
        return ''

NOTION_API = 'https://api.notion.com/v1'
NOTION_VERSION = '2025-09-03'
ACADEMIC_DS_ID = os.environ.get(
    'NOTION_DS_ID', '345e02e6-3ad9-819a-9e7d-000b18947124')
FETCH_LOOKAHEAD_DAYS = 90
# 달이 바뀔 무렵에 '이번 달 남은 일정'이 비어 버리는 문제가 있어,
# 달 경계와 상관없이 앞으로 이만큼의 기간에 있는 주요 일정을 모아 보여 준다.
UPCOMING_DAYS = 45
UPCOMING_MAX = 14
# 이 교시를 마치고 점심시간이다. 시간표를 오전·오후로 나누는 기준으로 쓴다.
LUNCH_AFTER_PERIOD = 4

# 학교 교표. 선생님 PC가 인터넷 그림을 받지 못하는 곳에서도 보이도록
# 파일 안에 그림 자체를 함께 싣는다.
SCHOOL_EMBLEM = (
    'data:image/png;base64,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'
)

KST = datetime.timezone(datetime.timedelta(hours=9))

CATEGORY_COLORS = {
    '공휴일': '#e74c3c', '학교행사': '#3498db', '수업': '#27ae60',
    '평가/고사': '#f39c12', '교육활동': '#9b59b6', '기타': '#7f8c8d',
}
IMPORTANT_CATEGORIES = {'학교행사', '평가/고사', '교육활동'}
WEEKDAY_KR = ['월', '화', '수', '목', '금', '토', '일']

NEIS_DEFAULTS = {
    'atpt_code': 'Q10',
    'school_code': '7140315',
    'school_name': '전남미래국제고등학교',
    'year': 2026,
    'semester': 2,
    'department': '설비시스템과',
    'grade': 1,
    'class_nm': '1',
}


def env_required(name):
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f'필수 환경변수 누락: {name}')
    return v


def request_with_ssl_fallback(method, url, **kwargs):
    fn = getattr(requests, method.lower())
    try:
        return fn(url, timeout=30, verify=certifi.where(), **kwargs)
    except requests.exceptions.SSLError:
        return fn(url, timeout=30, verify=False, **kwargs)


# ============== Notion 학사일정 =================
def fetch_notion_events(token, ds_id, start_iso, end_iso):
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json; charset=utf-8',
        'Notion-Version': NOTION_VERSION,
    }
    url = f'{NOTION_API}/data_sources/{ds_id}/query'
    results, cursor = [], None
    while True:
        payload = {
            'filter': {'and': [
                {'property': '날짜', 'date': {'on_or_after': start_iso}},
                {'property': '날짜', 'date': {'on_or_before': end_iso}},
            ]},
            'sorts': [{'property': '날짜', 'direction': 'ascending'}],
            'page_size': 100,
        }
        if cursor:
            payload['start_cursor'] = cursor
        r = request_with_ssl_fallback(
            'POST', url,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers=headers,
        )
        if r.status_code >= 400:
            raise RuntimeError(f'Notion HTTP {r.status_code}: {r.text[:500]}')
        j = r.json()
        results.extend(j.get('results', []))
        if not j.get('has_more'):
            break
        cursor = j.get('next_cursor')
    return results


def parse_event(page):
    props = page.get('properties', {})
    title_arr = props.get('행사명', {}).get('title', [])
    title = ''.join(t.get('plain_text', '') for t in title_arr).strip() or '(제목 없음)'
    date_obj = props.get('날짜', {}).get('date') or {}
    cat = (props.get('구분', {}).get('select') or {}).get('name', '')
    memo_arr = props.get('메모', {}).get('rich_text', []) or []
    memo = ''.join(t.get('plain_text', '') for t in memo_arr).strip()
    return {
        'title': title,
        'start': date_obj.get('start'),
        'end': date_obj.get('end'),
        'category': cat,
        'memo': memo,
    }


# ============== NEIS =================
def neis_get(endpoint, params):
    url = f'https://open.neis.go.kr/hub/{endpoint}'
    try:
        r = request_with_ssl_fallback('GET', url, params=params)
    except Exception as e:
        print(f'  NEIS {endpoint} 요청 실패: {e}')
        return None
    if r.status_code != 200:
        print(f'  NEIS {endpoint} HTTP {r.status_code}: {r.text[:200]}')
        return None
    try:
        j = r.json()
    except ValueError:
        print(f'  NEIS {endpoint} JSON 파싱 실패: {r.text[:200]}')
        return None
    # 인증키 오류나 '자료 없음'은 최상위 RESULT로만 오기 때문에,
    # 아래 반복문(목록 안의 head)만 보면 원인을 알 수 없이 조용히 넘어간다.
    top = j.get('RESULT')
    if isinstance(top, dict):
        code = top.get('CODE', '')
        msg = top.get('MESSAGE', '')
        if code and code != 'INFO-000':
            print(f'  NEIS {endpoint} {code}: {msg}')
            return None

    for key, val in j.items():
        if not isinstance(val, list):
            continue
        for item in val:
            if 'head' in item:
                for h in item['head']:
                    if 'RESULT' in h:
                        code = h['RESULT'].get('CODE', '')
                        msg = h['RESULT'].get('MESSAGE', '')
                        if code != 'INFO-000':
                            print(f'  NEIS {endpoint} {code}: {msg}')
                            return None
    return j


def _timetable_rows(neis_cfg, api_key, ymd, semester):
    j = neis_get('hisTimetable', {
        'KEY': api_key, 'Type': 'json',
        'pIndex': '1', 'pSize': '50',
        'ATPT_OFCDC_SC_CODE': neis_cfg['atpt_code'],
        'SD_SCHUL_CODE': neis_cfg['school_code'],
        'AY': str(neis_cfg['year']),
        'SEM': str(semester),
        'GRADE': str(neis_cfg['grade']),
        'CLASS_NM': str(neis_cfg['class_nm']),
        'DDDEP_NM': neis_cfg['department'],
        'TI_FROM_YMD': ymd, 'TI_TO_YMD': ymd,
    })
    if j and 'hisTimetable' in j:
        for item in j['hisTimetable']:
            if 'row' in item:
                return item['row']
    return []


def fetch_timetable(neis_cfg, api_key, ymd):
    # 설정된 학기로 먼저 찾고, 자료가 없으면 다른 학기로 한 번 더 찾는다.
    # 8월 개학처럼 학기가 바뀌는 시기에 설정을 고치지 않아도 시간표가 나오도록 한다.
    first = int(neis_cfg['semester'])
    rows = _timetable_rows(neis_cfg, api_key, ymd, first)
    if not rows:
        other = 2 if first == 1 else 1
        rows = _timetable_rows(neis_cfg, api_key, ymd, other)
        if rows:
            print(f'  NEIS 시간표를 {other}학기 기준으로 찾았습니다(설정값은 {first}학기).')
    rows.sort(key=lambda r: int(r.get('PERIO') or 0))
    return [{'period': r.get('PERIO'), 'content': (r.get('ITRT_CNTNT') or '').strip()}
            for r in rows]


def fetch_meals(neis_cfg, api_key, ymd):
    j = neis_get('mealServiceDietInfo', {
        'KEY': api_key, 'Type': 'json',
        'pIndex': '1', 'pSize': '20',
        'ATPT_OFCDC_SC_CODE': neis_cfg['atpt_code'],
        'SD_SCHUL_CODE': neis_cfg['school_code'],
        'MLSV_FROM_YMD': ymd, 'MLSV_TO_YMD': ymd,
    })
    rows = []
    if j and 'mealServiceDietInfo' in j:
        for item in j['mealServiceDietInfo']:
            if 'row' in item:
                rows = item['row']; break
    order = {'조식': 0, '중식': 1, '석식': 2}
    rows.sort(key=lambda r: order.get(r.get('MMEAL_SC_NM'), 99))
    out = []
    for r in rows:
        menu_raw = (r.get('DDISH_NM') or '').replace('<br/>', '\n')
        menu_lines = [m.strip() for m in menu_raw.split('\n') if m.strip()]
        out.append({
            'name': r.get('MMEAL_SC_NM') or '',
            'menu': menu_lines,
            'cal': r.get('CAL_INFO') or '',
        })
    return out


# ============== 학사일정 분류 =================
def event_covers(ev, day_iso):
    s = (ev.get('start') or '')[:10]
    e = (ev.get('end') or s)[:10]
    return bool(s) and s <= day_iso <= e


def classify(events, today, tomorrow, week_start, week_end, upcoming_end):
    today_s, tomorrow_s = today.isoformat(), tomorrow.isoformat()
    sec_t, sec_m, sec_w, sec_o = [], [], [], []
    seen_t, seen_m, seen_w, seen_o = set(), set(), set(), set()

    def k(ev): return (ev.get('title'), ev.get('start'))

    for ev in events:
        if not ev.get('start'):
            continue
        if event_covers(ev, today_s) and k(ev) not in seen_t:
            sec_t.append(ev); seen_t.add(k(ev))
        if event_covers(ev, tomorrow_s) and k(ev) not in seen_m:
            sec_m.append(ev); seen_m.add(k(ev))
        s_d = datetime.date.fromisoformat(ev['start'][:10])
        e_d = datetime.date.fromisoformat((ev.get('end') or ev['start'])[:10])
        if not (e_d < week_start or s_d > week_end):
            if k(ev) not in seen_w:
                sec_w.append(ev); seen_w.add(k(ev))
        if ev.get('category') in IMPORTANT_CATEGORIES:
            if not (e_d < today or s_d > upcoming_end):
                if k(ev) not in seen_o:
                    sec_o.append(ev); seen_o.add(k(ev))
    return sec_t, sec_m, sec_w, sec_o


# ============== HTML 렌더 =================
PAGE_CSS = """
/* 바깥에서 글꼴을 받아 오지 않는다.
   학교 망에서 그 요청이 막히면 브라우저가 스타일이 다 올 때까지 스크립트 실행을
   미루기 때문에, 화면이 반쯤 그려진 채로 한참 멈춰 있게 된다.
   윈도우와 맥에 이미 들어 있는 글꼴만 쓰면 그런 일이 생기지 않는다. */

:root{
  --ink:#131b24; --paper:#f2efe9; --card:#ffffff;
  --line:#e3ded4; --line-2:#efebe3;
  --text:#1a222c; --muted:#69737f; --faint:#9aa3ad;
  --teal:#0e6f61; --teal-bg:#e8f2f0;
  --amber:#a95a08; --amber-bg:#fbf1e3;
  --today:#1d4f7c; --today-bg:#eaf1f8;
  --radius:14px;
  --shadow:0 1px 2px rgba(19,27,36,.04), 0 10px 28px rgba(19,27,36,.055);
  --mono:ui-monospace, 'Cascadia Mono', 'Segoe UI Mono', Consolas, 'D2Coding', 'Courier New', monospace;
  --sans:'Pretendard','Malgun Gothic','맑은 고딕','Apple SD Gothic Neo',system-ui,sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0}
body{
  font-family:var(--sans); background:var(--paper); color:var(--text);
  -webkit-font-smoothing:antialiased;
  background-image:
    radial-gradient(1100px 420px at 12% -12%, rgba(14,111,97,.075), transparent 62%),
    radial-gradient(900px 380px at 90% -8%, rgba(169,90,8,.07), transparent 60%);
  background-attachment:fixed;
}
.shell{max-width:1780px;margin:0 auto;padding:10px 26px 10px}

/* ---- 상단 바 ---- */
.topbar{display:flex;align-items:center;gap:18px;background:var(--ink);color:#f6f4ef;
  border-radius:14px;padding:9px 20px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.topbar::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(118deg,rgba(255,255,255,.07),transparent 44%)}
.brand{display:flex;align-items:center;gap:13px;position:relative}
.mark{display:flex;align-items:center;justify-content:center;background:#f6f4ef;
  border-radius:10px;padding:5px 9px;box-shadow:0 1px 3px rgba(0,0,0,.25)}
.mark img{display:block;height:32px;width:auto}
.brand h1{margin:0;font-size:20px;font-weight:700;letter-spacing:-.01em;line-height:1.2}
.brand p{margin:2px 0 0;font-size:13px;color:#a5b0bc}
.sp{flex:1}
.relaunch{background:var(--amber-bg);border:1px solid #eddcc2;border-radius:11px;
  padding:8px 14px;margin-bottom:10px;font-size:13px;color:var(--amber);font-weight:600}
.daypill{text-align:right;position:relative}
.daypill .dow{display:block;font-size:11.5px;color:#a5b0bc;letter-spacing:.28em;margin-bottom:1px}
.daypill .d{font-family:var(--mono);font-size:23px;font-weight:600;letter-spacing:.02em;line-height:1.1}

/* ---- 공통 패널 ---- */
.panel{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);overflow:hidden;display:flex;flex-direction:column;min-width:0}
.panel-head{display:flex;align-items:center;gap:11px;padding:7px 18px;border-bottom:1px solid var(--line-2)}
.panel-head h2{margin:0;font-size:17px;font-weight:700;letter-spacing:-.01em}
.panel-head .sub{font-size:13px;color:var(--muted)}
.tag{font-family:var(--mono);font-size:11.5px;color:var(--muted);border:1px solid var(--line);
  border-radius:20px;padding:3px 10px;letter-spacing:.04em;white-space:nowrap}
.panel-body{padding:10px 18px 12px;flex:1;min-height:0}
#mealPanel{display:flex;flex-direction:column}
.empty{color:var(--faint);font-size:14px;padding:10px 2px;line-height:1.7}

/* ---- 하단 보조 영역 ---- */
.aux{display:grid;grid-template-columns:1.5fr 1.05fr .95fr;gap:12px;margin-top:10px;align-items:stretch}
@media (max-width:1400px){.aux{grid-template-columns:1fr 1fr}}
@media (max-width:900px){.aux{grid-template-columns:1fr}}

/* 시간표 */
.periods{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}
.period{border:1px solid var(--line);border-radius:11px;padding:7px 10px;background:#fcfbf9}
.period .num{display:block;font-family:var(--mono);font-size:11.5px;font-weight:600;
  color:var(--teal);letter-spacing:.06em}
.period .subj{display:block;font-size:15px;font-weight:500;margin-top:4px;line-height:1.35}
.period.rest{background:var(--amber-bg);border-color:#ecdcc3}
.period.rest .subj{color:var(--amber);font-style:italic}
.lunch{margin:8px 0;display:flex;align-items:center;gap:11px;color:var(--amber);
  font-size:12.5px;font-weight:600;letter-spacing:.08em}
.lunch::before,.lunch::after{content:"";flex:1;height:1px;
  background:repeating-linear-gradient(90deg,#e8dcc6 0 5px,transparent 5px 10px)}
@media (max-width:1400px){.periods{grid-template-columns:repeat(3,1fr)}}
@media (max-width:520px){.periods{grid-template-columns:repeat(2,1fr)}}

/* 급식 */
.mtabs{display:flex;align-items:center;gap:6px;margin-bottom:10px}
.mtabs .kcal{margin-left:auto}
.mtab{font-size:13.5px;font-weight:600;padding:7px 16px;border-radius:20px;border:1px solid var(--line);
  background:#fff;color:var(--muted);cursor:pointer;font-family:var(--sans);transition:.14s}
.mtab:hover{border-color:var(--ink);color:var(--text)}
.mtab.on{background:var(--ink);border-color:var(--ink);color:#f6f4ef}
.kcal{font-family:var(--mono);font-size:11.5px;color:var(--muted);
  border:1px solid var(--line);border-radius:20px;padding:3px 10px;white-space:nowrap}
.mpane{display:flex;flex-direction:column;min-height:0}
.mpane[hidden]{display:none}
.mpane ul{margin:0;padding-left:18px;font-size:15px;line-height:1.68;color:#39424e;
  max-height:104px;overflow-y:auto}
.mpane ul::-webkit-scrollbar{width:6px}
.mpane ul::-webkit-scrollbar-thumb{background:#ddd7cc;border-radius:6px}
.mpane li::marker{color:var(--amber)}
.mnote{margin-top:auto;padding-top:9px;font-size:12.5px;color:var(--faint)}

/* 다가오는 주요 일정 */
.mlist{max-height:114px;overflow-y:auto;padding-right:4px;min-height:0}
.mlist::-webkit-scrollbar{width:6px}
.mlist::-webkit-scrollbar-thumb{background:#ddd7cc;border-radius:6px}
.mmore{margin-top:auto;padding-top:9px;font-size:12.5px;color:var(--faint)}
.mrow{display:flex;gap:10px;align-items:baseline;padding:7px 0;border-top:1px dotted var(--line)}
.mrow:first-child{border-top:0;padding-top:2px}
.mrow .d{font-family:var(--mono);font-size:12px;color:var(--muted);min-width:76px;letter-spacing:.02em}
.mrow .t{font-size:14.5px;font-weight:500;line-height:1.45}
.mrow .cat{font-size:11px;padding:2px 9px;border-radius:20px;white-space:nowrap}

footer{margin-top:6px;text-align:center;color:var(--faint);font-size:11.5px;
  font-family:var(--mono);letter-spacing:.04em}
"""


def fmt_date(ev):
    s = (ev.get('start') or '')[:10]
    e = (ev.get('end') or '')[:10]
    if not s:
        return ''
    sd = datetime.date.fromisoformat(s)
    out = f'{sd.month}/{sd.day}({WEEKDAY_KR[sd.weekday()]})'
    if e and e != s:
        ed = datetime.date.fromisoformat(e)
        out += f'~{ed.month}/{ed.day}'
    return out


def _period_card(t):
    content = t['content'] or '—'
    content_class = 'rest' if any(
        k in content for k in ('휴업', '공휴', '연휴', '방학', '어린이날', '개교기념')
    ) else ''
    return (
        f'<div class="period {content_class}">'
        f'<span class="num">{html.escape(str(t["period"]))}교시</span>'
        f'<span class="subj">{html.escape(content)}</span></div>'
    )


def _period_no(t):
    try:
        return int(t['period'])
    except (TypeError, ValueError):
        return 99


def render_timetable_panel(timetable, dept_label):
    if not timetable:
        body = ('<div class="empty">NEIS에 등록된 오늘 시간표가 없습니다.<br>'
                '학교에서 시간표를 NEIS에 올리면 자동으로 표시됩니다.</div>')
    else:
        # 4교시를 마치고 점심을 먹으므로 오전과 오후를 나누어 보여 준다.
        morning = [t for t in timetable if _period_no(t) <= LUNCH_AFTER_PERIOD]
        afternoon = [t for t in timetable if _period_no(t) > LUNCH_AFTER_PERIOD]
        parts = []
        if morning:
            parts.append('<div class="periods">' + ''.join(_period_card(t) for t in morning) + '</div>')
        if morning and afternoon:
            parts.append('<div class="lunch">점심시간</div>')
        if afternoon:
            parts.append('<div class="periods">' + ''.join(_period_card(t) for t in afternoon) + '</div>')
        body = ''.join(parts)
    return (
        '<article class="panel">'
        '<div class="panel-head"><h2>오늘의 시간표</h2>'
        f'<span class="sub">{html.escape(dept_label)}</span><span class="sp"></span>'
        f'<span class="tag">{len(timetable)}교시</span></div>'
        f'<div class="panel-body">{body}</div></article>'
    )


def render_meal_panel(meals):
    """교사에게는 중식이 가장 중요하므로 중식을 먼저 펼치고, 조식과 석식은 넘겨 본다."""
    if not meals:
        body = ('<div class="empty">NEIS에 등록된 오늘 급식이 없습니다.<br>'
                '영양 담당 선생님이 식단을 NEIS에 올리면 자동으로 표시됩니다.</div>')
        return ('<article class="panel">'
                '<div class="panel-head"><h2>오늘의 급식</h2><span class="sp"></span>'
                '<span class="tag">0끼</span></div>'
                f'<div class="panel-body">{body}</div></article>')

    default_idx = next((i for i, m in enumerate(meals) if '중식' in (m.get('name') or '')), 0)
    tabs, panes = [], []
    for i, m in enumerate(meals):
        on = ' on' if i == default_idx else ''
        tabs.append(f'<button type="button" class="mtab{on}" data-meal="{i}" '
                    f'data-kcal="{html.escape(m.get("cal") or "")}">'
                    f'{html.escape(m.get("name") or "")}</button>')
        items = ''.join(f'<li>{html.escape(x)}</li>' for x in m.get('menu', []))
        hidden = '' if i == default_idx else ' hidden'
        panes.append(f'<div class="mpane" data-pane="{i}"{hidden}><ul>{items}</ul></div>')

    note = '' if len(meals) < 2 else '<div class="mnote">조식과 석식은 위 단추로 넘겨 보실 수 있습니다.</div>'
    return (
        '<article class="panel">'
        '<div class="panel-head"><h2>오늘의 급식</h2><span class="sp"></span>'
        f'<span class="tag">{len(meals)}끼</span></div>'
        '<div class="panel-body" id="mealPanel">'
        f'<div class="mtabs">{"".join(tabs)}'
        f'<span class="kcal" id="mealKcal">{html.escape(meals[default_idx].get("cal") or "")}</span>'
        f'</div>{"".join(panes)}{note}'
        '</div></article>'
    )


def render_month_panel(events):
    """달 경계에 걸리지 않도록, 오늘 이후의 주요 일정을 날짜 순으로 보여 준다."""
    events = sorted(events, key=lambda e: ((e.get('start') or '')[:10], e.get('title') or ''))
    total = len(events)
    shown = events[:UPCOMING_MAX]
    if not shown:
        rows = '<div class="empty">앞으로 45일 안에 예정된 주요 일정이 없습니다.</div>'
    else:
        out = []
        for ev in shown:
            cat = ev.get('category') or '기타'
            color = CATEGORY_COLORS.get(cat, '#7f8c8d')
            out.append(
                f'<div class="mrow"><span class="d">{html.escape(fmt_date(ev))}</span>'
                f'<span class="t">{html.escape(ev.get("title") or "")}</span>'
                f'<span class="sp"></span>'
                f'<span class="cat" style="background:{color}14;color:{color}">{html.escape(cat)}</span>'
                f'</div>'
            )
        rows = '<div class="mlist">' + ''.join(out) + '</div>'
        if total > len(shown):
            rows += ('<div class="mmore">이 밖에 %d건이 더 있습니다. 노션 학사일정에서 확인해 주세요.</div>'
                     % (total - len(shown)))
    return (
        '<article class="panel">'
        '<div class="panel-head"><h2>다가오는 주요 일정</h2><span class="sp"></span>'
        f'<span class="tag">{total}건</span></div>'
        f'<div class="panel-body">{rows}</div></article>'
    )


TAIL_SCRIPT = """
<script>
(function(){
  /* 이 스크립트는 문서의 맨 끝에 있어야 한다.
     예전 판본이 document.write 로 이 문서를 밀어 넣는 경우, 앞쪽에 스크립트가
     있으면 그 지점에서 문서가 잘려 나가기 때문이다.

     예전 판본은 문서만 바꿀 뿐 창(window)은 그대로 두므로, 예전 문서가 걸어 둔
     setInterval 이 끊기지 않고 살아남는다. 그 타이머가 깨어나 예전 방식으로
     화면을 덮어써 버리기 때문에, 여기에서 남아 있는 타이머를 모두 끊는다.

     이 문서의 시작 함수들은 타이머를 바로 걸지 않고 미뤄 두었다가, 정리가 끝난
     뒤에 여기에서 실행한다. 그래야 방금 건 타이머까지 함께 끊기지 않는다. */
  var last = 0;
  try{
    last = setTimeout(function(){}, 0);
    for(var i = 1; i <= last; i++){ clearTimeout(i); clearInterval(i); }
  }catch(e){}
  /* 이 문서가 그려지기 전에 이미 타이머가 있었다면, 예전 판본에서 넘어온 화면이다. */
  window.__jneReborn = (last > 1) || !!window.__jneBooted;
  window.__jneBooted = true;

  var starters = window.__jneInits || [];
  window.__jneInits = [];
  for(var k = 0; k < starters.length; k++){
    try{ starters[k](); }catch(e2){}
  }

  if(window.__jneReborn){
    var shell = document.querySelector('.shell');
    if(shell && !document.getElementById('relaunchNote')){
      var d = document.createElement('div');
      d.id = 'relaunchNote';
      d.className = 'relaunch';
      d.textContent = '이 화면은 예전 판본에서 넘어온 것입니다. 학사일정브리핑 프로그램을 한 번 닫았다가 다시 실행하시면 이 줄이 사라집니다.';
      shell.insertBefore(d, shell.firstChild);
    }
  }
})();
</script>
"""


MEAL_SCRIPT = """
<script>
/* 급식 구역을 새 발행본으로 바꿔 끼운 뒤에도 다시 연결해야 하므로 이름을 붙여 둔다. */
window.bindMealTabs=function(){
  var p=document.getElementById('mealPanel');
  if(!p)return;
  var tabs=p.querySelectorAll('.mtab'), panes=p.querySelectorAll('.mpane');
  var kc=document.getElementById('mealKcal');
  function show(i){
    for(var k=0;k<tabs.length;k++){tabs[k].className='mtab'+(k===i?' on':'');}
    for(var k=0;k<panes.length;k++){if(k===i){panes[k].removeAttribute('hidden');}else{panes[k].setAttribute('hidden','');}}
    if(kc)kc.textContent=tabs[i].getAttribute('data-kcal')||'';
  }
  for(var k=0;k<tabs.length;k++){
    (function(i){tabs[i].onclick=function(){show(i);};})(k);
  }
};
window.bindMealTabs();
</script>
"""


def gist_raw_url(filename):
    """게시된 gist 파일의 주소. 저장소에 주소를 적지 않고 환경 변수로 만든다."""
    direct = os.environ.get('BRIEFING_SELF_URL')
    if direct:
        return direct.strip()
    owner = (os.environ.get('GITHUB_REPOSITORY_OWNER') or '').strip()
    gist_id = (os.environ.get('GIST_ID') or '').strip()
    if owner and gist_id:
        return f'https://gist.githubusercontent.com/{owner}/{gist_id}/raw/{filename}'
    return ''


def self_refresh_url():
    return gist_raw_url('dashboard.html')


def render_loader(stamp, dashboard_url):
    """선생님 PC에 저장되는 briefing.html 은 화면을 담지 않고 껍데기만 담는다.

    프로그램은 실행할 때 이 파일을 한 번 내려받아 저장한다. 예전에는 이 파일에
    화면 전체가 들어 있어서, 화면을 고칠 때마다 모든 PC에서 프로그램을 다시
    실행해야 했다. 이제 이 파일은 최신 화면(dashboard.html)을 받아 오는 일만
    하므로, 앞으로 화면을 고쳐도 프로그램을 다시 실행할 필요가 없다.

    문서에 발행 표식을 함께 남겨 둔다. 예전 판본이 열려 있는 화면도 이 표식을
    보고 스스로 이 껍데기로 바뀌므로, 그때부터는 최신 화면을 따라오게 된다.
    """
    if not dashboard_url:
        return ''
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="briefing-build" content="{html.escape(stamp)}">
<title>교무실 브리핑</title>
<style>
  html,body{{margin:0;height:100%%}}
  body{{background:#f2efe9;color:#69737f;display:flex;align-items:center;justify-content:center;
    font-family:'Pretendard','Malgun Gothic','맑은 고딕','Apple SD Gothic Neo',system-ui,sans-serif}}
  .box{{text-align:center;font-size:15px;line-height:1.8;padding:24px}}
  .box b{{display:block;font-size:18px;color:#131b24;margin-bottom:6px}}
  .box.err{{color:#a95a08}}
</style>
</head>
<body>
<div class="box" id="msg"><b>교무실 브리핑</b>화면을 불러오는 중입니다…</div>
<script>
(function(){{
  var SRC={json.dumps(dashboard_url)};
  function fail(t){{
    var m=document.getElementById('msg');
    if(m){{m.className='box err';m.innerHTML='<b>브리핑을 불러오지 못했습니다</b>'+t;}}
  }}
  var KEY='jneBriefingCache';
  function show(t){{document.open();document.write(t);document.close();}}
  function cached(){{try{{return window.localStorage.getItem(KEY);}}catch(e){{return null;}}}}
  function keep(t){{try{{window.localStorage.setItem(KEY,t);}}catch(e){{}}}}
  if(!window.fetch){{fail('이 컴퓨터의 브라우저가 오래되었습니다. 크롬으로 열어 주세요.');return;}}
  var url=SRC+(SRC.indexOf('?')<0?'?':'&')+'t='+(new Date()).getTime();
  fetch(url,{{cache:'no-store'}}).then(function(r){{
    if(!r.ok)throw new Error(r.status);
    return r.text();
  }}).then(function(t){{
    if(!t||t.length<500)throw new Error('empty');
    keep(t);show(t);
  }}).catch(function(){{
    /* 인터넷이 막혀 있으면 마지막으로 받아 둔 화면이라도 보여 준다. */
    var old=cached();
    if(old&&old.length>500){{show(old);return;}}
    fail('인터넷 연결을 확인하신 뒤 F5 를 눌러 다시 시도해 주세요.');
  }});
}})();
</script>
</body></html>
"""


def build_auto_refresh(url, stamp):
    """열려 있는 화면이 스스로 최신 발행본을 확인해 바뀐 구역만 갈아 끼우도록 한다.

    배부한 프로그램은 실행할 때 한 번만 파일을 내려받기 때문에, 아침에 띄워 둔
    화면은 하루 종일 그대로 남는다. 이 스크립트가 있으면 프로그램을 다시 실행하지
    않아도 발행 시각(06시, 13시)의 새 내용이 화면에 반영된다.

    처음에는 document.write 로 문서 전체를 다시 썼는데, 그 방식에는 문제가 두 가지
    있었다. 다시 쓰는 동안 화면이 잠깐 깨져 보였고, 열어 둔 입력 창과 적어 넣던
    내용이 함께 사라졌다. 또 gist 를 나누어 맡은 서버끼리 응답이 어긋나면 두 판본을
    번갈아 받아 끝없이 다시 쓰기도 했다.

    그래서 지금은 세 가지를 지킨다. 발행 표식이 지금 화면보다 뒤일 때에만 바꾸고,
    입력 창이 열려 있거나 글자를 적고 있는 동안에는 손대지 않으며, 문서를 버리지 않고
    보조 영역과 날짜 표시처럼 실제로 바뀌는 자리만 갈아 끼운다.
    """
    if not url:
        return ''
    return (
        '<script>\n'
        '(function(){\n'
        '  var SRC=' + json.dumps(url) + ';\n'
        '  var MINE=' + json.dumps(stamp) + ';\n'
        '  function busy(){\n'
        '    var p=document.getElementById("wpPanel");\n'
        '    if(p&&p.className.indexOf("wp-open")>=0)return true;\n'
        '    var a=document.activeElement;\n'
        '    return !!(a&&(a.tagName==="TEXTAREA"||a.tagName==="INPUT"));\n'
        '  }\n'
        '  function put(cur,html){\n'
        '    if(cur&&cur.innerHTML!==html){cur.innerHTML=html;return true;}\n'
        '    return false;\n'
        '  }\n'
        '  function swap(doc){\n'
        '    var touched=false;\n'
        '    [".aux","footer",".daypill",".brand"].forEach(function(sel){\n'
        '      var cur=document.querySelector(sel),nxt=doc.querySelector(sel);\n'
        '      if(cur&&nxt&&put(cur,nxt.innerHTML))touched=true;\n'
        '    });\n'
        '    var cs=document.querySelectorAll("style"),ns=doc.querySelectorAll("style");\n'
        '    if(cs.length===ns.length){\n'
        '      for(var i=0;i<cs.length;i++){\n'
        '        if(cs[i].textContent!==ns[i].textContent)cs[i].textContent=ns[i].textContent;\n'
        '      }\n'
        '    }\n'
        '    var btn=document.getElementById("wpBtnInput");\n'
        '    var live=btn&&btn.style.display==="";\n'
        '    if(!live){\n'
        '      var c=document.getElementById("wpContent"),n=doc.getElementById("wpContent");\n'
        '      if(c&&n)put(c,n.innerHTML);\n'
        '    }\n'
        '    if(doc.title&&document.title!==doc.title)document.title=doc.title;\n'
        '    if(touched&&window.bindMealTabs)window.bindMealTabs();\n'
        '  }\n'
        '  function check(){\n'
        '    if(!window.fetch||!window.DOMParser||document.hidden||busy())return;\n'
        '    fetch(SRC,{cache:"no-store"}).then(function(r){return r.text();}).then(function(t){\n'
        '      var m=t.match(/name="briefing-build" content="([^"]*)"/);\n'
        '      var s=m?m[1]:"";\n'
        '      if(!s||s<=MINE||t.length<500)return;\n'
        '      var doc=new DOMParser().parseFromString(t,"text/html");\n'
        '      if(!doc||!doc.querySelector(".aux"))return;\n'
        '      swap(doc);MINE=s;\n'
        '    }).catch(function(){});\n'
        '  }\n'
        '  function start(){setTimeout(check,20000);setInterval(check,10*60*1000);}\n'
        '  window.__jneInits=window.__jneInits||[];\n'
        '  window.__jneInits.push(start);\n'
        '})();\n'
        '</script>'
    )


def render_html(today, sections, timetable, meals, school, school_year, dept_label, generated_at,
                workplan_html=''):
    # 오늘·내일·다음 주 일정은 주간 업무 계획의 '주요일정' 행에 그대로 실리므로
    # 중복을 없애고, 앞으로의 주요 일정 목록만 보조 영역에 남긴다.
    sec_o = sections[3]
    dow = WEEKDAY_KR[today.weekday()]
    date_str = today.strftime('%Y. %m. %d.')
    aux = (render_timetable_panel(timetable, dept_label)
           + render_meal_panel(meals)
           + render_month_panel(sec_o))
    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="briefing-build" content="{html.escape(generated_at)}">
<title>교무실 브리핑 — {date_str}</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="shell">
  <header class="topbar">
    <div class="brand">
      <span class="mark"><img src="{SCHOOL_EMBLEM}" alt="전남미래국제고등학교 교표"></span>
      <div>
        <h1>교무실 브리핑</h1>
        <p>{html.escape(school)} · {html.escape(school_year)}</p>
      </div>
    </div>
    <span class="sp"></span>
    <div class="daypill">
      <span class="dow">{dow}요일</span>
      <span class="d">{date_str}</span>
    </div>
  </header>
{workplan_html}
  <section class="aux">{aux}</section>
  <footer>갱신 {html.escape(generated_at)} KST · 노션 학사일정 + NEIS Open API</footer>
</div>
{MEAL_SCRIPT}
{build_auto_refresh(self_refresh_url(), generated_at)}
{TAIL_SCRIPT}
</body></html>'''


# ============== Gist =================
def upload_to_gist(token, gist_id, files_dict):
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'JNE-Briefing-Publisher',
    }
    url = f'https://api.github.com/gists/{gist_id}'
    body = {'files': {fn: {'content': content} for fn, content in files_dict.items()}}
    r = request_with_ssl_fallback(
        'PATCH', url,
        data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
        headers=headers,
    )
    if r.status_code >= 400:
        raise RuntimeError(f'Gist HTTP {r.status_code}: {r.text[:500]}')
    return r.json()


# ============== main =================
def main():
    notion_token = env_required('NOTION_TOKEN')
    neis_api_key = env_required('NEIS_API_KEY')
    gist_token = env_required('GIST_TOKEN')
    gist_id = env_required('GIST_ID')

    neis_cfg = dict(NEIS_DEFAULTS)
    for k in list(neis_cfg.keys()):
        env_v = os.environ.get(f'NEIS_{k.upper()}')
        if env_v is not None:
            neis_cfg[k] = env_v

    now_kst = datetime.datetime.now(KST)
    today = now_kst.date()
    tomorrow = today + datetime.timedelta(days=1)
    end = today + datetime.timedelta(days=FETCH_LOOKAHEAD_DAYS)
    print(f'=== {now_kst.isoformat(timespec="seconds")} 발행 시작 (KST) ===')
    print(f'  Notion fetch {today} ~ {end}')

    pages = fetch_notion_events(notion_token, ACADEMIC_DS_ID,
                                today.isoformat(), end.isoformat())
    events = [parse_event(p) for p in pages if p.get('properties')]
    print(f'  events={len(events)}')

    days_until = (7 - today.weekday()) % 7 or 7
    week_start = today + datetime.timedelta(days=days_until)
    week_end = week_start + datetime.timedelta(days=6)
    upcoming_end = today + datetime.timedelta(days=UPCOMING_DAYS)
    sections = classify(events, today, tomorrow, week_start, week_end, upcoming_end)
    print(f'  분류: 오늘 {len(sections[0])} / 내일 {len(sections[1])} / '
          f'다음주 {len(sections[2])} / 다가오는주요 {len(sections[3])}')

    ymd_today = today.strftime('%Y%m%d')
    timetable = fetch_timetable(neis_cfg, neis_api_key, ymd_today)
    meals = fetch_meals(neis_cfg, neis_api_key, ymd_today)
    print(f'  NEIS 시간표 {len(timetable)}교시 / 급식 {len(meals)}끼')

    generated_at = now_kst.isoformat(timespec='seconds')
    school = neis_cfg.get('school_name', '전남미래국제고등학교')
    school_year = f'{neis_cfg["year"]}학년도'
    dept_label = (
        f'{neis_cfg["department"]} '
        f'{neis_cfg["grade"]}학년 {neis_cfg["class_nm"]}반'
    )
    workplan_html = build_workplan_section()

    html_str = render_html(
        today, sections, timetable, meals,
        school, school_year, dept_label, generated_at,
        workplan_html=workplan_html,
    )

    json_payload = {
        'generated_at': generated_at,
        'generated_date': today.isoformat(),
        'lookahead_days': FETCH_LOOKAHEAD_DAYS,
        'school': school,
        'school_year': school_year,
        'department': neis_cfg['department'],
        'events': events,
        'timetable': timetable,
        'meals': meals,
    }
    json_str = json.dumps(json_payload, ensure_ascii=False, indent=2)

    dashboard_url = self_refresh_url()
    files = {
        # 프로그램이 내려받는 파일. 최신 화면을 받아 오는 껍데기만 담는다.
        'briefing.html': render_loader(generated_at, dashboard_url) or html_str,
        # 실제 화면. 앞으로 이 파일만 바꾸면 모든 PC에 그대로 반영된다.
        'dashboard.html': html_str,
        'briefing.json': json_str,
    }
    if not dashboard_url:
        print('  [주의] gist 주소를 만들 수 없어 예전 방식으로 briefing.html 에 화면을 그대로 실었습니다.')
    upload_to_gist(gist_token, gist_id, files)
    print(f'  gist 업로드 완료: https://gist.github.com/{gist_id}')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
