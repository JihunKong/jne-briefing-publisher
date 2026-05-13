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

NOTION_API = 'https://api.notion.com/v1'
NOTION_VERSION = '2025-09-03'
ACADEMIC_DS_ID = os.environ.get(
    'NOTION_DS_ID', '345e02e6-3ad9-819a-9e7d-000b18947124')
FETCH_LOOKAHEAD_DAYS = 90

KST = datetime.timezone(datetime.timedelta(hours=9))

CATEGORY_COLORS = {
    '공휴일': '#e74c3c', '학교행사': '#3498db', '수업': '#27ae60',
    '평가/고사': '#f39c12', '교육활동': '#9b59b6', '기타': '#7f8c8d',
}
IMPORTANT_CATEGORIES = {'학교행사', '평가/고사', '교육활동'}
WEEKDAY_KR = ['월', '화', '수', '목', '금', '토', '일']

NEIS_DEFAULTS = {
    'atpt_code': 'Q10',
    'school_code': '8490586',
    'school_name': '전남미래국제고등학교',
    'year': 2026,
    'semester': 1,
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


def fetch_timetable(neis_cfg, api_key, ymd):
    j = neis_get('hisTimetable', {
        'KEY': api_key, 'Type': 'json',
        'pIndex': '1', 'pSize': '50',
        'ATPT_OFCDC_SC_CODE': neis_cfg['atpt_code'],
        'SD_SCHUL_CODE': neis_cfg['school_code'],
        'AY': str(neis_cfg['year']),
        'SEM': str(neis_cfg['semester']),
        'GRADE': str(neis_cfg['grade']),
        'CLASS_NM': str(neis_cfg['class_nm']),
        'DDDEP_NM': neis_cfg['department'],
        'TI_FROM_YMD': ymd, 'TI_TO_YMD': ymd,
    })
    rows = []
    if j and 'hisTimetable' in j:
        for item in j['hisTimetable']:
            if 'row' in item:
                rows = item['row']; break
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


def classify(events, today, tomorrow, week_start, week_end, month_end):
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
            if not (e_d < today or s_d > month_end):
                if k(ev) not in seen_o:
                    sec_o.append(ev); seen_o.add(k(ev))
    return sec_t, sec_m, sec_w, sec_o


# ============== HTML 렌더 =================
def fmt_date(ev):
    s = (ev.get('start') or '')[:10]
    e = (ev.get('end') or '')[:10]
    if not s:
        return ''
    sd = datetime.date.fromisoformat(s)
    out = f'{sd.month}/{sd.day}({WEEKDAY_KR[sd.weekday()]})'
    if e and e != s:
        ed = datetime.date.fromisoformat(e)
        out += f' ~ {ed.month}/{ed.day}({WEEKDAY_KR[ed.weekday()]})'
    return out


def card(ev):
    cat = ev.get('category') or '기타'
    color = CATEGORY_COLORS.get(cat, '#7f8c8d')
    memo = ev.get('memo') or ''
    memo_html = f'<div class="memo">{html.escape(memo)}</div>' if memo else ''
    return (
        f'<div class="card">'
        f'<div class="card-head">'
        f'<span class="badge" style="background:{color};">{html.escape(cat)}</span>'
        f'<span class="date">{html.escape(fmt_date(ev))}</span></div>'
        f'<div class="title">{html.escape(ev.get("title") or "")}</div>'
        f'{memo_html}</div>'
    )


def section(name, icon, color, events, empty_msg):
    if events:
        cards = ''.join(card(e) for e in events)
    else:
        cards = f'<div class="empty">{html.escape(empty_msg)}</div>'
    return (
        f'<section><h2 style="border-color:{color};">'
        f'<span class="icon" style="background:{color};">{icon}</span>'
        f'{html.escape(name)}<span class="count">{len(events)}건</span></h2>'
        f'<div class="cards">{cards}</div></section>'
    )


def render_timetable_section(timetable, dept_label):
    if not timetable:
        body = f'<div class="empty">오늘 시간표 정보가 없습니다.</div>'
    else:
        rows = []
        for t in timetable:
            content = t['content'] or '—'
            content_class = 'rest' if any(
                k in content for k in ('휴업', '공휴', '연휴', '방학', '어린이날', '개교기념')
            ) else ''
            rows.append(
                f'<div class="period {content_class}">'
                f'<span class="num">{html.escape(str(t["period"]))}교시</span>'
                f'<span class="subj">{html.escape(content)}</span></div>'
            )
        body = '<div class="periods">' + ''.join(rows) + '</div>'
    return (
        f'<section><h2 style="border-color:#16a085;">'
        f'<span class="icon" style="background:#16a085;">📚</span>'
        f'오늘의 시간표 <span class="dept">({html.escape(dept_label)})</span>'
        f'<span class="count">{len(timetable)}교시</span></h2>{body}</section>'
    )


def render_meals_section(meals):
    if not meals:
        body = f'<div class="empty">오늘 급식 정보가 없습니다.</div>'
    else:
        items = []
        for m in meals:
            menu_html = ''.join(
                f'<li>{html.escape(line)}</li>' for line in m['menu']
            )
            cal = m['cal']
            cal_badge = f'<span class="cal">{html.escape(cal)}</span>' if cal else ''
            items.append(
                f'<div class="meal">'
                f'<div class="meal-head"><span class="meal-name">{html.escape(m["name"])}</span>'
                f'{cal_badge}</div>'
                f'<ul class="menu">{menu_html}</ul></div>'
            )
        body = '<div class="meals-grid">' + ''.join(items) + '</div>'
    return (
        f'<section><h2 style="border-color:#e67e22;">'
        f'<span class="icon" style="background:#e67e22;">🍱</span>'
        f'오늘의 급식<span class="count">{len(meals)}끼</span></h2>{body}</section>'
    )


def render_html(today, sections, timetable, meals, school, school_year, dept_label, generated_at):
    sec_t, sec_m, sec_w, sec_o = sections
    today_str = today.strftime(f'%Y년 %m월 %d일 ({WEEKDAY_KR[today.weekday()]})')
    body = (
        section('오늘', '🔴', '#e74c3c', sec_t, '오늘 등록된 일정이 없습니다.') +
        section('내일', '🟡', '#f39c12', sec_m, '내일 등록된 일정이 없습니다.') +
        render_timetable_section(timetable, dept_label) +
        render_meals_section(meals) +
        section('다음 주', '🟢', '#27ae60', sec_w, '다음 주 일정이 없습니다.') +
        section('이번 달 남은 중요 일정', '🔵', '#3498db', sec_o,
                '이번 달 남은 중요 일정이 없습니다.')
    )
    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>학사일정 브리핑 — {today_str}</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:'Pretendard','Malgun Gothic',sans-serif;background:#f5f6fa;
       margin:0;padding:32px;color:#2c3e50;max-width:1100px;margin:0 auto}}
  header{{background:linear-gradient(135deg,#667eea,#764ba2);color:white;
         padding:28px 32px;border-radius:16px;margin:32px 0 24px;
         box-shadow:0 8px 24px rgba(102,126,234,.3)}}
  header h1{{margin:0 0 6px;font-size:28px}}
  header .sub{{opacity:.9;font-size:15px}}
  section{{background:white;border-radius:12px;padding:20px 24px;
          margin-bottom:18px;box-shadow:0 2px 8px rgba(0,0,0,.05)}}
  section h2{{margin:0 0 16px;padding-bottom:12px;border-bottom:3px solid;
             display:flex;align-items:center;gap:10px;font-size:19px;flex-wrap:wrap}}
  .icon{{display:inline-flex;align-items:center;justify-content:center;
        width:30px;height:30px;border-radius:8px;color:white;font-size:14px;
        flex-shrink:0}}
  .dept{{font-size:14px;color:#7f8c8d;font-weight:normal}}
  .count{{margin-left:auto;font-size:13px;font-weight:normal;color:#7f8c8d;
         background:#ecf0f1;padding:3px 10px;border-radius:10px}}
  .cards{{display:flex;flex-direction:column;gap:10px}}
  .card{{border:1px solid #e1e8ed;border-radius:10px;padding:14px 16px;
        transition:all .15s}}
  .card:hover{{border-color:#3498db;transform:translateX(2px)}}
  .card-head{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
  .badge{{color:white;font-size:12px;padding:3px 10px;border-radius:10px;
         font-weight:600}}
  .date{{color:#7f8c8d;font-size:13px;font-weight:500}}
  .title{{font-size:16px;font-weight:600;margin-bottom:4px}}
  .memo{{color:#5d6d7e;font-size:14px;margin-top:4px}}
  .empty{{color:#95a5a6;font-style:italic;padding:8px 4px}}
  .periods{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));
           gap:8px}}
  .period{{display:flex;flex-direction:column;gap:4px;padding:10px 12px;
          border:1px solid #e1e8ed;border-radius:8px;background:#fafbfc}}
  .period .num{{font-size:11px;font-weight:700;color:#16a085;letter-spacing:.5px}}
  .period .subj{{font-size:14px;font-weight:500}}
  .period.rest{{background:#fef5e7;border-color:#f8c471}}
  .period.rest .subj{{color:#a04000;font-style:italic}}
  .meals-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
              gap:12px}}
  .meal{{border:1px solid #e1e8ed;border-radius:10px;padding:14px 16px;
        background:#fffaf0}}
  .meal-head{{display:flex;align-items:center;gap:10px;margin-bottom:8px;
             padding-bottom:8px;border-bottom:1px dashed #ecdba8}}
  .meal-name{{font-weight:700;color:#d35400;font-size:15px}}
  .cal{{margin-left:auto;font-size:11px;color:#7f8c8d;background:#fff;
       padding:2px 8px;border-radius:8px;border:1px solid #ecdba8}}
  .menu{{margin:0;padding-left:18px;font-size:13px;color:#5d4037;line-height:1.7}}
  .menu li{{margin:0}}
  footer{{text-align:center;color:#95a5a6;font-size:12px;margin-top:24px;padding:0 0 32px}}
</style>
</head>
<body>
<header><h1>📅 오늘의 학사일정 브리핑</h1>
<div class="sub">{html.escape(school)} · {html.escape(school_year)} · {today_str}</div></header>
{body}
<footer>캐시 갱신 {html.escape(generated_at)} KST · 데이터 출처: 노션 학사일정 + NEIS Open API</footer>
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
    if today.month == 12:
        month_end = datetime.date(today.year, 12, 31)
    else:
        month_end = datetime.date(today.year, today.month + 1, 1) - datetime.timedelta(days=1)
    sections = classify(events, today, tomorrow, week_start, week_end, month_end)
    print(f'  분류: 오늘 {len(sections[0])} / 내일 {len(sections[1])} / '
          f'다음주 {len(sections[2])} / 이번달중요 {len(sections[3])}')

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
    html_str = render_html(
        today, sections, timetable, meals,
        school, school_year, dept_label, generated_at,
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

    upload_to_gist(gist_token, gist_id, {
        'briefing.html': html_str,
        'briefing.json': json_str,
    })
    print(f'  gist 업로드 완료: https://gist.github.com/{gist_id}')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
