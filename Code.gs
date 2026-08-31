/************************************************************************
 * 2026학년도 주간·월간 업무 계획 → 노션 자동 정리 (Google Apps Script)
 *
 * ■ 설치 순서 (최초 1회)
 *   1. 이 파일 전체를 시트의 [확장 프로그램 → Apps Script] 편집기에 붙여 넣고 저장합니다.
 *   2. 시트로 돌아가 새로 고침하면 [📋 업무계획] 메뉴가 나타납니다.
 *      메뉴에서 [① 초기 설정]을 실행하고 권한을 승인합니다. (탭·양식이 자동 생성됩니다)
 *   3. https://www.notion.so/profile/integrations 에서 내부 통합(Internal Integration)을
 *      만들고, 발급된 시크릿을 [② 노션 토큰 설정]에 붙여 넣습니다.
 *   4. 노션의 '📋 주간·월간 업무 계획' 데이터베이스 페이지에서 우측 상단 ⋯ → 연결(Connections)
 *      → 방금 만든 통합을 추가합니다.
 *   5. [③ 연결 테스트]로 확인한 뒤 [④ 자동 전송 켜기]를 실행하면 설치가 끝납니다.
 *
 * ■ 버전
 *   2026-08-31-a: 월간 탭을 '월중 행사 계획' 달력(일~토 7열)으로 바꾸고,
 *                 노션 학사일정 달력과 날짜 단위로 양방향 동기화한다.
 *   2026-08-24-e: 노션 '학사일정' 달력과 주간 탭 '주요일정' 행의 양방향 동기화.
 *                 달력 일정은 📅 표식으로 시트에 자동 반영되고(원본은 달력),
 *                 시트에 직접 적은 주요일정 항목은 달력에 자동 등록된 뒤
 *                 📅 항목으로 바뀌어 순환이 생기지 않습니다.
 *   2026-08-24-d: 대시보드 웹 API 추가(doGet/doPost). [배포 → 새 배포 → 웹 앱,
 *                 실행: 나, 액세스: 모든 사용자]로 배포하면 게시용 대시보드가
 *                 실시간 조회와 직접 입력에 사용할 수 있는 주소(/exec)가 생깁니다.
 *   2026-08-24-c: 초기 설정의 열 고정 오류(병합 충돌) 수정, 템플릿 재생성 안전화,
 *                 연결 테스트를 토큰 단계와 데이터베이스 접근 단계로 나누어 진단 강화.
 *
 * ■ 동작 방식
 *   - 주간 탭(부서×요일)과 월간 탭(부서×주차)을 저장하면, 10분 안에 노션
 *     데이터베이스에 주차별·월별 페이지로 자동 반영됩니다.
 *   - 노션 페이지의 '✍️ 메모·의견' 제목 아래에 적은 내용은 자동 갱신 시에도 유지됩니다.
 *   - 매주 지정 요일 아침에 다음 주 탭이, 매월 지정일 아침에 다음 달 월간 탭이
 *     자동으로 생성됩니다. (설정 탭에서 변경 가능)
 ************************************************************************/

var CONFIG = {
  NOTION_VERSION: '2026-03-11',
  TZ: 'Asia/Seoul',
  DEFAULT_DB_URL: 'https://www.notion.so/3ab2bc8d07c348bfa899184995671576',
  CAL_DB_URL_DEFAULT: 'https://www.notion.so/345e02e63ad981a685c8f672bb81b028',
  CAL_MARKER: '📅 ',
  MAJOR_ROW_NAME: '주요일정',
  SETTINGS_SHEET: '설정',
  TPL_WEEK: '템플릿_주간',
  TPL_MONTH: '템플릿_월간',
  WEEK_TITLE: '주간 업무 계획',
  MONTH_TITLE: '월중 행사 계획',
  MONTH_TITLE_OLD: '월간 업무 계획',
  MARKER: '✍️ 메모·의견',
  DEPTS: ['주요일정', '교무기획', '교육정보', '특성화', '학생자치인권\n(보건,상담,급식)', '행정실', '교장·교감'],
  DAY_LABELS: ['월', '화', '수', '목', '금', '토~일'],
  CAL_DOW: ['일', '월', '화', '수', '목', '금', '토'],
  CAL_WEEKS: 6,
  WEEK_ICON: '📅',
  MONTH_ICON: '🗓️',
  WEEK_TAB_COLOR: '#4a86c8',
  MONTH_TAB_COLOR: '#8e6bbf',
  SYNC_EVERY_MINUTES: 10,
  HOUSEKEEPING_HOUR: 6
};

/* =====================================================================
 * 1. 메뉴
 * =================================================================== */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('📋 업무계획')
    .addItem('① 초기 설정(탭·양식 만들기)', 'initializeAll')
    .addItem('② 노션 토큰 설정', 'setNotionToken')
    .addItem('③ 연결 테스트', 'testConnection')
    .addItem('④ 자동 전송 켜기', 'enableAutoSync')
    .addSeparator()
    .addItem('현재 탭 지금 전송', 'syncActiveSheetMenu')
    .addItem('모든 탭 다시 전송', 'syncAllTabsMenu')
    .addSeparator()
    .addItem('다음 주 탭 만들기', 'createNextWeekTabMenu')
    .addItem('특정 주 탭 만들기', 'createWeekTabPromptMenu')
    .addItem('다음 달 월간 탭 만들기', 'createNextMonthTabMenu')
    .addSeparator()
    .addItem('월중 행사 계획 PDF 내려받기', 'monthCalendarPdfMenu')
    .addItem('월중 행사 달력 양식 다시 만들기', 'rebuildMonthCalendarMenu')
    .addSeparator()
    .addItem('자동 전송 끄기', 'disableAutoSync')
    .addToUi();
}

/* =====================================================================
 * 2. 날짜 유틸 (순수 함수)
 * =================================================================== */

function pad2(n) { return (n < 10 ? '0' : '') + n; }
function isoOf(y, m, d) { return y + '-' + pad2(m) + '-' + pad2(d); }
function parseIso(s) {
  var m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(String(s).trim());
  return m ? { y: +m[1], m: +m[2], d: +m[3] } : null;
}
function toUtc(iso) { var p = parseIso(iso); return Date.UTC(p.y, p.m - 1, p.d); }
function fromUtc(ms) {
  var dt = new Date(ms);
  return isoOf(dt.getUTCFullYear(), dt.getUTCMonth() + 1, dt.getUTCDate());
}
function addDays(iso, n) { return fromUtc(toUtc(iso) + n * 86400000); }
function weekdayOf(iso) { return new Date(toUtc(iso)).getUTCDay(); } // 0=일
function mondayOf(iso) {
  var w = weekdayOf(iso);
  return addDays(iso, w === 0 ? -6 : 1 - w);
}
function lastDayOfMonth(y, m) { return new Date(Date.UTC(y, m, 0)).getUTCDate(); }
/* 달력 격자의 첫 칸(그 달 1일이 속한 주의 일요일) */
function calFirstSunday(y, m) {
  var first = isoOf(y, m, 1);
  return addDays(first, -weekdayOf(first));
}
function md(iso) { var p = parseIso(iso); return p.m + '/' + p.d; }
function mdDot(iso) { var p = parseIso(iso); return p.m + '.' + p.d; }

/* 주차 규칙: '기준 요일(offset)'이 속한 달을 그 주의 달로 본다. 기본 수요일(offset 2) */
function weekMonth(mondayIso, offset) {
  var p = parseIso(addDays(mondayIso, offset));
  return { y: p.y, m: p.m };
}
function weekIndex(mondayIso, offset) {
  var p = parseIso(addDays(mondayIso, offset));
  return Math.floor((p.d - 1) / 7) + 1;
}
function weekLabel(mondayIso, offset) {
  var wm = weekMonth(mondayIso, offset);
  return wm.m + '월 ' + weekIndex(mondayIso, offset) + '주';
}
/* 해당 (y,m)월에 속하는 모든 주의 월요일 목록 */
function weeksOfMonth(y, m, offset) {
  var anchorWeekday = (1 + offset) % 7;
  var first = isoOf(y, m, 1);
  var delta = (anchorWeekday - weekdayOf(first) + 7) % 7;
  var a = addDays(first, delta);
  var res = [];
  while (true) {
    var p = parseIso(a);
    if (p.y !== y || p.m !== m) break;
    res.push(addDays(a, -offset));
    a = addDays(a, 7);
  }
  return res;
}

/* =====================================================================
 * 3. 시트 파서 (순수 함수: 문자열 격자를 입력받는다)
 * =================================================================== */

function cellStr(v) { return v === null || v === undefined ? '' : String(v).trim(); }

function parseWeeklyValues(grid) {
  var r0 = -1;
  for (var i = 0; i < grid.length; i++) {
    if (cellStr(grid[i][0]) === '요일') { r0 = i; break; }
  }
  if (r0 < 0) throw new Error("주간 탭에서 '요일' 행을 찾지 못했습니다. 양식이 변형되지 않았는지 확인해 주세요.");
  var depts = [];
  var notes = '';
  for (var r = r0 + 2; r < grid.length; r++) {
    var label = cellStr(grid[r][0]);
    if (!label) break;
    if (label.replace(/\s/g, '').indexOf('전달') === 0) {
      notes = cellStr(grid[r][1]);
      break;
    }
    depts.push({
      name: label,
      days: grid[r].slice(1, 8).slice(0, 6).map(cellStr)
    });
  }
  return { depts: depts, notes: notes };
}

/* 월중 행사 달력 탭 읽기 (순수 함수)
 * 반환: { days: { 'yyyy-mm-dd': ['행사명', ...] }, notes: '월간 전달사항' } */
function parseMonthlyCalendar(grid, y, m) {
  var r0 = calHeaderRow(grid);
  if (r0 < 0) {
    throw new Error("월중 행사 계획 탭에서 요일 머리글 줄을 찾지 못했습니다. 양식이 변형되지 않았는지 확인해 주세요.");
  }
  var sun = calFirstSunday(y, m);
  var ym = isoOf(y, m, 1).slice(0, 7);
  var days = {};
  for (var w = 0; w < CONFIG.CAL_WEEKS; w++) {
    var cRow = r0 + 2 + w * 2;
    if (cRow >= grid.length) break;
    for (var c = 0; c < 7; c++) {
      var iso = addDays(sun, w * 7 + c);
      if (iso.slice(0, 7) !== ym) continue;
      days[iso] = splitLines(cellStr(grid[cRow][c]));
    }
  }
  var notes = '';
  var nRow = r0 + 1 + CONFIG.CAL_WEEKS * 2;
  for (var r = nRow; r < Math.min(grid.length, nRow + 3); r++) {
    if (cellStr(grid[r][0]).replace(/\s/g, '').indexOf('전달') >= 0) {
      notes = cellStr(grid[r][1]);
      break;
    }
  }
  return { days: days, notes: notes };
}

/* 요일 머리글 줄의 0-based 인덱스 (없으면 -1) */
function calHeaderRow(grid) {
  for (var i = 0; i < grid.length; i++) {
    if (cellStr(grid[i][0]) === CONFIG.CAL_DOW[0] &&
        grid[i].length >= 7 && cellStr(grid[i][6]) === CONFIG.CAL_DOW[6]) return i;
  }
  return -1;
}

function chunkText(text, size) {
  var s = String(text == null ? '' : text);
  size = size || 1900;
  if (!s) return [];
  var out = [];
  for (var i = 0; i < s.length; i += size) out.push(s.slice(i, i + size));
  return out;
}
function rt(text, ann) {
  var chunks = chunkText(text);
  if (!chunks.length) return [];
  return chunks.map(function (c) {
    var o = { type: 'text', text: { content: c } };
    if (ann) o.annotations = ann;
    return o;
  });
}
function rtLink(text, url) {
  return [{ type: 'text', text: { content: String(text), link: { url: url } } }];
}
function pageMention(pageId) {
  return [{ type: 'mention', mention: { type: 'page', page: { id: pageId } } }];
}
function para(rich) { return { type: 'paragraph', paragraph: { rich_text: rich } }; }
function h2(text) { return { type: 'heading_2', heading_2: { rich_text: rt(text) } }; }
function h3(text) { return { type: 'heading_3', heading_3: { rich_text: rt(text) } }; }
function bullet(rich, children) {
  var b = { type: 'bulleted_list_item', bulleted_list_item: { rich_text: rich } };
  if (children && children.length) b.bulleted_list_item.children = children;
  return b;
}
function calloutBlock(richArr, emoji, color, children) {
  var b = {
    type: 'callout',
    callout: { rich_text: richArr, icon: { type: 'emoji', emoji: emoji }, color: color || 'blue_background' }
  };
  if (children && children.length) b.callout.children = children;
  return b;
}
function dividerBlock() { return { type: 'divider', divider: {} }; }
function toggleBlock(summary, children) {
  return { type: 'toggle', toggle: { rich_text: rt(summary), children: children } };
}
function tableBlock(width, rows, hasColHeader, hasRowHeader) {
  return {
    type: 'table',
    table: {
      table_width: width,
      has_column_header: hasColHeader !== false,
      has_row_header: hasRowHeader !== false,
      children: rows.map(function (cells) {
        var padded = cells.slice(0, width);
        while (padded.length < width) padded.push([]);
        return { type: 'table_row', table_row: { cells: padded } };
      })
    }
  };
}
function markerBlocks() {
  return [
    dividerBlock(),
    h3(CONFIG.MARKER),
    para(rt('이 제목 아래에 적은 내용은 자동 갱신 시에도 지워지지 않습니다. 의견이나 댓글을 자유롭게 남겨 주세요.', { color: 'gray' }))
  ];
}
function splitLines(text) {
  return String(text || '').split(/\r?\n/).map(function (s) { return s.trim(); }).filter(function (s) { return s; });
}
function oneLine(name) { return String(name || '').replace(/\s*\n\s*/g, ' '); }
/* 부서명 축약: 줄바꿈이나 괄호 앞부분만 취한다. 예) '학생자치인권\n(보건,상담,급식)' → '학생자치인권' */
function shortName(name) {
  return String(name || '').split('\n')[0].split('(')[0].trim() || oneLine(name);
}

/* 주간 페이지 본문
 * 가독성 원칙:
 *  1) 전달·협의사항을 노란 상자로 맨 위에 둔다.
 *  2) '요일별 한눈에 보기'를 표보다 먼저 둔다. 휴대전화에서 세로로 읽힌다.
 *  3) 원본 양식 표는 마지막에 둔다. (노션 API는 표의 열 너비를 지정할 수 없어
 *     7열 표는 좁게 렌더링되므로, 표를 첫 화면에 두지 않는다)
 */
function buildWeeklyBlocks(week, opts) {
  var mon = week.mondayIso;
  var dates = [0, 1, 2, 3, 4].map(function (i) { return addDays(mon, i); });
  var sat = addDays(mon, 5), sun = addDays(mon, 6);

  var blocks = [];

  // 1) 기간 안내
  var calloutRich = rt('기간: ' + mdDot(mon) + '.(월) ~ ' + mdDot(sun) + '.(일) · 구글 시트를 수정하면 이 페이지가 자동 갱신됩니다.  ')
    .concat(opts && opts.sheetUrl ? rtLink('↗ 시트에서 편집', opts.sheetUrl) : []);
  blocks.push(calloutBlock(calloutRich, '📌', 'blue_background'));

  // 2) 전달·협의사항 (있을 때만, 노란 상자로 강조)
  var noteLines = splitLines(week.notes);
  if (noteLines.length) {
    blocks.push(calloutBlock(
      rt('전달·협의사항', { bold: true }),
      '📣', 'yellow_background',
      noteLines.map(function (line) { return bullet(rt(line)); })
    ));
  }

  // 3) 요일별 한눈에 보기
  var dayBullets = [];
  for (var c = 0; c < 6; c++) {
    var items = [];
    week.depts.forEach(function (d) {
      splitLines(d.days[c]).forEach(function (line) {
        items.push(bullet(rt(shortName(d.name), { bold: true }).concat(rt(' · ' + line))));
      });
    });
    if (!items.length) continue;
    var label = c < 5
      ? CONFIG.DAY_LABELS[c] + ' ' + md(dates[c])
      : '토~일 ' + md(sat) + '~' + md(sun);
    dayBullets.push(bullet(rt(label, { bold: true }), items));
  }
  if (dayBullets.length && !(opts && opts.includeDaily === false)) {
    blocks.push(h3('📅 요일별 한눈에 보기'));
    blocks = blocks.concat(dayBullets);
  }

  // 4) 부서별 표 (원본 양식)
  var header = ['부서'];
  for (var i = 0; i < 5; i++) header.push(CONFIG.DAY_LABELS[i] + ' ' + md(dates[i]));
  header.push('토~일 ' + md(sat) + '~' + md(sun));
  var rows = [header.map(function (hcell) { return rt(hcell); })];
  week.depts.forEach(function (d) {
    var row = [rt(d.name)]; // 부서명 줄바꿈을 유지해서 첫 열이 넓어지지 않게 한다
    for (var c2 = 0; c2 < 6; c2++) row.push(rt(d.days[c2] || ''));
    rows.push(row);
  });
  blocks.push(h3('📋 부서별 표 (원본 양식)'));
  blocks.push(tableBlock(7, rows, true, true));

  return blocks;
}

/* 월간 페이지 본문 */
/* 노션 월간 페이지에 실을 달력 표의 줄 목록을 만든다 (순수 함수) */
function calTableRows(y, m, cal) {
  var sun = calFirstSunday(y, m);
  var ym = isoOf(y, m, 1).slice(0, 7);
  var rows = [CONFIG.CAL_DOW.map(function (d) { return rt(d); })];
  for (var w = 0; w < CONFIG.CAL_WEEKS; w++) {
    var row = [], any = false;
    for (var c = 0; c < 7; c++) {
      var iso = addDays(sun, w * 7 + c);
      if (iso.slice(0, 7) !== ym) { row.push(rt('')); continue; }
      any = true;
      var items = ((cal && cal.days && cal.days[iso]) || [])
        .map(function (t) { return String(t).replace(CONFIG.CAL_MARKER, ''); });
      var head = String(parseIso(iso).d);
      row.push(rt(items.length ? head + '\n' + items.join('\n') : head));
    }
    if (any) rows.push(row);
  }
  return rows;
}

function buildMonthlyBlocks(monthData, opts) {
  // monthData: { y, m, weeks:[mondayIso...], cal:{days,notes}|null,
  //              weekly:{ 'W2026-08-31': {depts,notes}, ... }, pageIds:{key:pageId} }
  var y = monthData.y, m = monthData.m;
  var weeks = monthData.weeks;
  var width = 1 + weeks.length;
  var blocks = [];

  var calloutRich = rt(y + '년 ' + m + '월 월중 행사 계획 · 학사일정 달력과 주간 취합이 자동으로 갱신됩니다.  ')
    .concat(opts && opts.sheetUrl ? rtLink('↗ 시트에서 편집', opts.sheetUrl) : []);
  blocks.push(calloutBlock(calloutRich, '🗓️', 'purple_background'));

  // 월간 전달사항은 표보다 먼저, 노란 상자로 강조한다
  if (monthData.cal && monthData.cal.notes) {
    blocks.push(calloutBlock(
      rt('월간 전달사항', { bold: true }),
      '📣', 'yellow_background',
      splitLines(monthData.cal.notes).map(function (line) { return bullet(rt(line)); })
    ));
  }

  function weekHeaderCells() {
    var cells = [rt('부서')];
    weeks.forEach(function (mon, i) {
      cells.push(rt((i + 1) + '주\n' + md(mon) + '~' + md(addDays(mon, 4))));
    });
    return cells;
  }

  blocks.push(h2('1️⃣ 월중 행사 계획'));
  var calRows = calTableRows(y, m, monthData.cal);
  if (calRows.length > 1) {
    blocks.push(tableBlock(7, calRows, true, false));
  } else {
    blocks.push(para(rt('(월중 행사 달력 탭이 아직 없습니다)', { color: 'gray' })));
  }

  blocks.push(h2('2️⃣ 부서별 주간 계획 취합'));
  var anyWeekly = weeks.some(function (mon) { return monthData.weekly['W' + mon]; });
  if (anyWeekly) {
    var deptList = []; // {key, display}
    weeks.forEach(function (mon) {
      var wk = monthData.weekly['W' + mon];
      if (!wk) return;
      wk.depts.forEach(function (d) {
        var key = oneLine(d.name);
        var found = deptList.some(function (x) { return x.key === key; });
        if (!found) deptList.push({ key: key, display: d.name });
      });
    });
    var rows2 = [weekHeaderCells()];
    deptList.forEach(function (dd) {
      var nm = dd.key;
      var row = [rt(dd.display)];
      weeks.forEach(function (mon) {
        var wk = monthData.weekly['W' + mon];
        if (!wk) { row.push(rt('(미입력)', { color: 'gray' })); return; }
        var dept = null;
        for (var i = 0; i < wk.depts.length; i++) {
          if (oneLine(wk.depts[i].name) === nm) { dept = wk.depts[i]; break; }
        }
        var lines = [];
        if (dept) {
          for (var c = 0; c < 6; c++) {
            if (!dept.days[c]) continue;
            var label = c < 5 ? CONFIG.DAY_LABELS[c] : '토~일';
            splitLines(dept.days[c]).forEach(function (line) { lines.push(label + ') ' + line); });
          }
        }
        row.push(rt(lines.join('\n')));
      });
      rows2.push(row);
    });
    // 전달·협의사항 행
    var noteRow = [rt('전달·협의')];
    weeks.forEach(function (mon) {
      var wk = monthData.weekly['W' + mon];
      var t = wk && wk.notes ? splitLines(wk.notes).join(' / ') : '';
      if (t.length > 500) t = t.slice(0, 500) + '…';
      noteRow.push(rt(t));
    });
    rows2.push(noteRow);
    blocks.push(tableBlock(width, rows2, true, true));
  } else {
    blocks.push(para(rt('(아직 이 달의 주간 탭이 없습니다. 주간 탭이 전송되면 자동으로 채워집니다)', { color: 'gray' })));
  }

  var linkBullets = [];
  weeks.forEach(function (mon, i) {
    var key = 'W' + mon;
    var pid = monthData.pageIds && monthData.pageIds[key];
    if (pid) {
      linkBullets.push(bullet(rt((i + 1) + '주: ').concat(pageMention(pid))));
    }
  });
  if (linkBullets.length) {
    blocks.push(h3('🔗 주차별 페이지'));
    blocks = blocks.concat(linkBullets);
  }
  return blocks;
}

/* =====================================================================
 * 5. 노션 API
 * =================================================================== */

function getToken_() {
  var t = PropertiesService.getScriptProperties().getProperty('NOTION_TOKEN');
  if (!t) throw new Error('노션 토큰이 없습니다. 메뉴 [② 노션 토큰 설정]을 먼저 실행해 주세요.');
  return t;
}

function notionFetch_(path, method, payload) {
  var attempt = 0;
  while (true) {
    var res = UrlFetchApp.fetch('https://api.notion.com' + path, {
      method: method,
      contentType: 'application/json',
      muteHttpExceptions: true,
      headers: {
        'Authorization': 'Bearer ' + getToken_(),
        'Notion-Version': CONFIG.NOTION_VERSION
      },
      payload: payload ? JSON.stringify(payload) : undefined
    });
    var code = res.getResponseCode();
    if (code < 300) {
      var text = res.getContentText();
      return text ? JSON.parse(text) : {};
    }
    if ((code === 429 || code >= 500) && attempt < 5) {
      var headers = res.getHeaders();
      var ra = Number(headers['Retry-After'] || headers['retry-after'] || 0);
      Utilities.sleep(ra ? ra * 1000 : Math.min(30000, 500 * Math.pow(2, attempt)) + Math.floor(Math.random() * 250));
      attempt++;
      continue;
    }
    if (code === 401) throw new Error('노션 토큰이 유효하지 않습니다(401). [② 노션 토큰 설정]에서 다시 입력해 주세요.');
    if (code === 404 || code === 403) throw new Error('노션에서 대상에 접근하지 못했습니다(' + code + '). 통합이 데이터베이스 페이지(또는 상위 페이지)의 ⋯ → 연결 메뉴에 추가되어 있는지, 통합을 학교 페이지가 있는 같은 워크스페이스에 만들었는지 확인해 주세요. [③ 연결 테스트]를 실행하면 원인을 단계별로 알려 줍니다.');
    throw new Error('노션 API 오류 ' + code + ': ' + res.getContentText().slice(0, 300));
  }
}

function extractDbId_(url) {
  var m = String(url || '').split('?')[0].replace(/-/g, '').match(/[0-9a-f]{32}/i);
  if (!m) throw new Error("설정 탭의 '노션 데이터베이스 URL'이 올바르지 않습니다.");
  return m[0].toLowerCase();
}

function getDataSourceId_(dbId) {
  var sp = PropertiesService.getScriptProperties();
  var cached = sp.getProperty('NOTION_DS_' + dbId);
  if (cached) return cached;
  var db = notionFetch_('/v1/databases/' + dbId, 'get');
  if (!db.data_sources || !db.data_sources.length) {
    throw new Error('데이터베이스에서 데이터 소스를 찾지 못했습니다.');
  }
  var ds = db.data_sources[0].id;
  sp.setProperty('NOTION_DS_' + dbId, ds);
  return ds;
}

function findPageByKey_(dsId, key) {
  var body = {
    filter: { property: '동기화 키', rich_text: { equals: key } },
    page_size: 1
  };
  var out = notionFetch_('/v1/data_sources/' + dsId + '/query', 'post', body);
  return out.results && out.results.length ? out.results[0].id : null;
}

function listChildren_(blockId) {
  var results = [];
  var cursor = null;
  do {
    var path = '/v1/blocks/' + blockId + '/children?page_size=100' + (cursor ? '&start_cursor=' + encodeURIComponent(cursor) : '');
    var out = notionFetch_(path, 'get');
    results = results.concat(out.results || []);
    cursor = out.has_more ? out.next_cursor : null;
  } while (cursor);
  return results;
}

function appendChildren_(blockId, blocks, position) {
  var lastId = null;
  for (var i = 0; i < blocks.length; i += 50) {
    var chunk = blocks.slice(i, i + 50);
    var body = { children: chunk };
    if (i === 0 && position) body.position = position;
    else if (lastId) body.position = { type: 'after_block', after_block: { id: lastId } };
    var out = notionFetch_('/v1/blocks/' + blockId + '/children', 'patch', body);
    var created = out.results || [];
    if (created.length) lastId = created[created.length - 1].id;
  }
}

function plainOf_(block) {
  var t = block[block.type] && block[block.type].rich_text;
  if (!t) return '';
  return t.map(function (r) { return r.plain_text || (r.text && r.text.content) || ''; }).join('');
}

/* 표식(✍️) 앞의 자동 생성 블록만 지우고 새 내용으로 교체한다 */
function replaceAutoContent_(pageId, autoBlocks) {
  var children = listChildren_(pageId);
  var markerIdx = -1;
  for (var i = 0; i < children.length; i++) {
    var b = children[i];
    if ((b.type === 'heading_3' || b.type === 'heading_2') && plainOf_(b).indexOf('✍️') === 0) {
      markerIdx = i;
      break;
    }
  }
  var toDelete = markerIdx >= 0 ? children.slice(0, markerIdx) : children;
  toDelete.forEach(function (b) {
    notionFetch_('/v1/blocks/' + b.id, 'delete');
    Utilities.sleep(120);
  });
  var payload = markerIdx >= 0 ? autoBlocks : autoBlocks.concat(markerBlocks());
  appendChildren_(pageId, payload, { type: 'start' });
}

function upsertPage_(dsId, key, icon, props, autoBlocks) {
  var pageId = findPageByKey_(dsId, key);
  if (pageId) {
    notionFetch_('/v1/pages/' + pageId, 'patch', { properties: props });
    replaceAutoContent_(pageId, autoBlocks);
  } else {
    var body = {
      parent: { type: 'data_source_id', data_source_id: dsId },
      icon: { type: 'emoji', emoji: icon },
      properties: props,
      children: autoBlocks.concat(markerBlocks())
    };
    var out = notionFetch_('/v1/pages', 'post', body);
    pageId = out.id;
  }
  // 대시보드에서 노션 페이지로 바로 갈 수 있도록 키→페이지 매핑을 기억한다
  try { PropertiesService.getScriptProperties().setProperty('NPAGE_' + key, pageId); } catch (e) { }
  return pageId;
}

/* =====================================================================
 * 6. 설정 읽기/상태 기록
 * =================================================================== */

function getSettings_(ss) {
  var sh = ss.getSheetByName(CONFIG.SETTINGS_SHEET);
  var map = {};
  if (sh) {
    var vals = sh.getDataRange().getValues();
    vals.forEach(function (r) {
      var k = cellStr(r[0]);
      if (k) map[k] = r.length > 1 ? r[1] : '';
    });
  }
  var offsetMap = { '월': 0, '화': 1, '수': 2, '목': 3, '금': 4, '토': 5, '일': 6 };
  var anchor = cellStr(map['주차의 소속 월 기준 요일']) || '수';
  return {
    dbUrl: cellStr(map['노션 데이터베이스 URL']) || CONFIG.DEFAULT_DB_URL,
    offset: (anchor in offsetMap) ? offsetMap[anchor] : 2,
    nextWeekDay: cellStr(map['다음 주 탭 생성 요일']) || '월',
    nextMonthDate: Number(map['다음 달 탭 생성일'] || 15),
    includeDaily: cellStr(map['요일별 보기 포함'] || map['부서별 토글 포함']) !== '아니오',
    dashPin: cellStr(map['대시보드 입력 비밀번호']),
    calDbUrl: cellStr(map['학사일정 데이터베이스 URL']) || CONFIG.CAL_DB_URL_DEFAULT,
    calPush: cellStr(map['학사일정 자동 등록']) !== '아니오'
  };
}

function setStatus_(ss, label, value) {
  var sh = ss.getSheetByName(CONFIG.SETTINGS_SHEET);
  if (!sh) return;
  var vals = sh.getRange('A1:A30').getValues();
  for (var i = 0; i < vals.length; i++) {
    if (cellStr(vals[i][0]) === label) {
      sh.getRange(i + 1, 2).setValue(value);
      return;
    }
  }
}

/* =====================================================================
 * 7. 탭 식별·읽기
 * =================================================================== */

function sheetType_(sheet) {
  var name = sheet.getName();
  if (name === CONFIG.SETTINGS_SHEET) return 'settings';
  if (name.indexOf('템플릿') === 0) return 'template';
  var a1 = cellStr(sheet.getRange('A1').getValue());
  if (a1 === CONFIG.WEEK_TITLE) return 'week';
  if (a1 === CONFIG.MONTH_TITLE || a1 === CONFIG.MONTH_TITLE_OLD) return 'month';
  return null;
}

function readAnchorIso_(ss, sheet) {
  var disp = cellStr(sheet.getRange('B2').getDisplayValue());
  var p = parseIso(disp);
  if (p) return isoOf(p.y, p.m, p.d);
  var v = sheet.getRange('B2').getValue();
  if (v instanceof Date) {
    return Utilities.formatDate(v, ss.getSpreadsheetTimeZone(), 'yyyy-MM-dd');
  }
  throw new Error("'" + sheet.getName() + "' 탭의 B2 칸에서 날짜를 읽지 못했습니다. yyyy-mm-dd 형식의 날짜인지 확인해 주세요.");
}

function normalizeGrid_(ss, sheet) {
  var tz = ss.getSpreadsheetTimeZone();
  return sheet.getDataRange().getValues().map(function (row) {
    return row.map(function (v) {
      if (v instanceof Date) return Utilities.formatDate(v, tz, 'M/d');
      return v === null || v === undefined ? '' : String(v);
    });
  });
}

function isoToSerial_(iso) {
  return Math.round((toUtc(iso) - Date.UTC(1899, 11, 30)) / 86400000);
}

function sheetUrlOf_(ss, sheet) {
  return ss.getUrl().split('#')[0] + '#gid=' + sheet.getSheetId();
}

function todayIso_() {
  return Utilities.formatDate(new Date(), CONFIG.TZ, 'yyyy-MM-dd');
}

function nowStamp_() {
  return Utilities.formatDate(new Date(), CONFIG.TZ, 'M/d HH:mm');
}

function nowIsoDateTime_() {
  return Utilities.formatDate(new Date(), CONFIG.TZ, "yyyy-MM-dd'T'HH:mm:ssXXX");
}

/* =====================================================================
 * 8. 동기화 본체
 * =================================================================== */

function makeCtx_(ss) {
  var st = getSettings_(ss);
  var dbId = extractDbId_(st.dbUrl);
  return {
    ss: ss,
    settings: st,
    dsId: getDataSourceId_(dbId)
  };
}

function syncWeeklySheet_(ctx, sheet, skipCalRefresh) {
  var ss = ctx.ss;
  var mondayIso = mondayOf(readAnchorIso_(ss, sheet));
  if (!skipCalRefresh) {
    try { refreshMajorScheduleRow_(ctx, sheet, mondayIso); } catch (eCal) { /* 상태 칸에 이미 기록됨 */ }
  }
  var grid = normalizeGrid_(ss, sheet);
  var parsed = parseWeeklyValues(grid);
  var off = ctx.settings.offset;
  var wm = weekMonth(mondayIso, off);
  var wi = weekIndex(mondayIso, off);
  var title = wm.m + '월 ' + wi + '주 (' + mdDot(mondayIso) + '.~' + mdDot(addDays(mondayIso, 4)) + '.)';
  var key = 'W' + mondayIso;
  var props = {
    '이름': { title: rt(title) },
    '구분': { select: { name: '주간' } },
    '월': { select: { name: wm.y + '년 ' + wm.m + '월' } },
    '주차': { number: wi },
    '기간': { date: { start: mondayIso, end: addDays(mondayIso, 6) } },
    '동기화 키': { rich_text: rt(key) },
    '시트': { url: sheetUrlOf_(ss, sheet) },
    '마지막 동기화': { date: { start: nowIsoDateTime_() } }
  };
  var blocks = buildWeeklyBlocks(
    { mondayIso: mondayIso, depts: parsed.depts, notes: parsed.notes },
    { sheetUrl: sheetUrlOf_(ss, sheet), includeDaily: ctx.settings.includeDaily }
  );
  var pageId = upsertPage_(ctx.dsId, key, CONFIG.WEEK_ICON, props, blocks);
  sheet.getRange('G2').setValue(nowStamp_() + ' ✔');
  return { key: key, pageId: pageId, mondayIso: mondayIso, y: wm.y, m: wm.m };
}

function findMonthlySheet_(ctx, y, m) {
  var sheets = ctx.ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheetType_(sheets[i]) !== 'month') continue;
    var p = parseIso(readAnchorIso_(ctx.ss, sheets[i]));
    if (p && p.y === y && p.m === m) return sheets[i];
  }
  return null;
}

function collectWeeklySheets_(ctx) {
  var out = {};
  ctx.ss.getSheets().forEach(function (sh) {
    if (sheetType_(sh) !== 'week') return;
    try {
      var mondayIso = mondayOf(readAnchorIso_(ctx.ss, sh));
      out['W' + mondayIso] = sh;
    } catch (e) { /* 날짜 없는 주간 탭은 무시 */ }
  });
  return out;
}

function syncMonth_(ctx, y, m) {
  var off = ctx.settings.offset;
  var weeks = weeksOfMonth(y, m, off);
  var weeklySheets = collectWeeklySheets_(ctx);
  var monthSheet = findMonthlySheet_(ctx, y, m);

  var weekly = {};
  var hasAnyWeek = false;
  weeks.forEach(function (mon) {
    var sh = weeklySheets['W' + mon];
    if (!sh) return;
    hasAnyWeek = true;
    weekly['W' + mon] = parseWeeklyValues(normalizeGrid_(ctx.ss, sh));
  });
  if (!monthSheet && !hasAnyWeek) return null;

  var cal = null;
  if (monthSheet) {
    try { refreshMonthCalendarSheet_(ctx, monthSheet, y, m); } catch (eCal) { }
    try { cal = parseMonthlyCalendar(normalizeGrid_(ctx.ss, monthSheet), y, m); } catch (eCal2) { }
  }

  var pageIds = {};
  weeks.forEach(function (mon) {
    var pid = findPageByKey_(ctx.dsId, 'W' + mon);
    if (pid) pageIds['W' + mon] = pid;
  });

  var key = 'M' + y + '-' + pad2(m);
  var title = y + '년 ' + m + '월 월중 행사 계획';
  var startIso = isoOf(y, m, 1);
  var endIso = isoOf(y, m, lastDayOfMonth(y, m));
  var sheetUrl = monthSheet ? sheetUrlOf_(ctx.ss, monthSheet) : ctx.ss.getUrl().split('#')[0];
  var props = {
    '이름': { title: rt(title) },
    '구분': { select: { name: '월간' } },
    '월': { select: { name: y + '년 ' + m + '월' } },
    '주차': { number: 0 },
    '기간': { date: { start: startIso, end: endIso } },
    '동기화 키': { rich_text: rt(key) },
    '시트': { url: sheetUrl },
    '마지막 동기화': { date: { start: nowIsoDateTime_() } }
  };
  var blocks = buildMonthlyBlocks(
    { y: y, m: m, weeks: weeks, cal: cal, weekly: weekly, pageIds: pageIds },
    { sheetUrl: sheetUrl }
  );
  var pageId = upsertPage_(ctx.dsId, key, CONFIG.MONTH_ICON, props, blocks);
  if (monthSheet) monthSheet.getRange('G2').setValue(nowStamp_() + ' ✔');
  return { key: key, pageId: pageId };
}

function syncSheet_(ctx, sheet) {
  var type = sheetType_(sheet);
  if (type === 'week') {
    var r = syncWeeklySheet_(ctx, sheet);
    syncMonth_(ctx, r.y, r.m);
    return r;
  }
  if (type === 'month') {
    var p = parseIso(readAnchorIso_(ctx.ss, sheet));
    return syncMonth_(ctx, p.y, p.m);
  }
  throw new Error("'" + sheet.getName() + "' 탭은 주간/월간 양식이 아니어서 전송하지 않았습니다.");
}

/* =====================================================================
 * 9. 메뉴 동작
 * =================================================================== */

function syncActiveSheetMenu() {
  var ss = SpreadsheetApp.getActive();
  var ui = SpreadsheetApp.getUi();
  try {
    var ctx = makeCtx_(ss);
    var sheet = ss.getActiveSheet();
    syncSheet_(ctx, sheet);
    setStatus_(ss, '마지막 자동 전송', nowStamp_() + ' (수동 전송)');
    setStatus_(ss, '마지막 오류', '없음');
    ui.alert('전송 완료', "'" + sheet.getName() + "' 탭을 노션에 반영했습니다.", ui.ButtonSet.OK);
  } catch (e) {
    setStatus_(ss, '마지막 오류', nowStamp_() + ' ' + e.message);
    ui.alert('전송 실패', e.message, ui.ButtonSet.OK);
  }
}

function syncAllTabsMenu() {
  var ss = SpreadsheetApp.getActive();
  var ui = SpreadsheetApp.getUi();
  try {
    var ctx = makeCtx_(ss);
    var months = {};
    var count = 0;
    ss.getSheets().forEach(function (sh) {
      if (sheetType_(sh) !== 'week') return;
      var r = syncWeeklySheet_(ctx, sh);
      months[r.y + '-' + r.m] = { y: r.y, m: r.m };
      count++;
    });
    ss.getSheets().forEach(function (sh) {
      if (sheetType_(sh) !== 'month') return;
      var p = parseIso(readAnchorIso_(ss, sh));
      months[p.y + '-' + p.m] = { y: p.y, m: p.m };
    });
    Object.keys(months).forEach(function (k) {
      syncMonth_(ctx, months[k].y, months[k].m);
    });
    setStatus_(ss, '마지막 자동 전송', nowStamp_() + ' (전체 전송)');
    setStatus_(ss, '마지막 오류', '없음');
    ui.alert('전송 완료', '주간 탭 ' + count + '개와 관련 월간 페이지를 모두 반영했습니다.', ui.ButtonSet.OK);
  } catch (e) {
    setStatus_(ss, '마지막 오류', nowStamp_() + ' ' + e.message);
    ui.alert('전송 실패', e.message, ui.ButtonSet.OK);
  }
}

function setNotionToken() {
  var ui = SpreadsheetApp.getUi();
  var res = ui.prompt('노션 토큰 설정',
    'notion.so/profile/integrations 에서 만든 내부 통합의 시크릿(ntn_ 또는 secret_으로 시작)을 붙여 넣으세요.\n' +
    '토큰은 이 스크립트의 속성에만 저장되며 시트에는 표시되지 않습니다.',
    ui.ButtonSet.OK_CANCEL);
  if (res.getSelectedButton() !== ui.Button.OK) return;
  var token = res.getResponseText().trim().replace(/^["']+|["']+$/g, '');
  if (!/^(ntn_|secret_)/.test(token)) {
    ui.alert('토큰 형식 확인', "입력한 값이 'ntn_' 또는 'secret_'으로 시작하지 않습니다. 통합 페이지의 시크릿을 다시 확인해 주세요.", ui.ButtonSet.OK);
    return;
  }
  PropertiesService.getScriptProperties().setProperty('NOTION_TOKEN', token);
  ui.alert('저장 완료', '노션 토큰을 저장했습니다. 이제 [③ 연결 테스트]를 실행해 주세요.', ui.ButtonSet.OK);
}

function testConnection() {
  var ss = SpreadsheetApp.getActive();
  var ui = SpreadsheetApp.getUi();

  // 1단계: 토큰 자체 확인 (통합 이름과 워크스페이스를 알아낸다)
  var self;
  try {
    var me = notionFetch_('/v1/users/me', 'get');
    self = {
      integration: me.name || '(이름 없음)',
      workspace: (me.bot && me.bot.workspace_name) || '(확인 불가)'
    };
  } catch (e1) {
    setStatus_(ss, '노션 연결', nowStamp_() + ' 실패(토큰 단계)');
    setStatus_(ss, '마지막 오류', nowStamp_() + ' ' + e1.message);
    ui.alert('연결 실패(토큰 단계)',
      '토큰 확인에 실패했습니다.\n' + e1.message +
      '\n\n통합 페이지(notion.so/profile/integrations)에서 시크릿을 다시 복사해 [② 노션 토큰 설정]에 붙여 넣어 주세요.',
      ui.ButtonSet.OK);
    return;
  }

  // 2단계: 데이터베이스 접근 확인
  try {
    var st = getSettings_(ss);
    var dbId = extractDbId_(st.dbUrl);
    PropertiesService.getScriptProperties().deleteProperty('NOTION_DS_' + dbId);
    var db = notionFetch_('/v1/databases/' + dbId, 'get');
    var title = (db.title && db.title.map(function (t) { return t.plain_text; }).join('')) || '(제목 없음)';
    getDataSourceId_(dbId);
    setStatus_(ss, '노션 연결', nowStamp_() + " 정상 ('" + title + "' ← 통합 '" + self.integration + "')");
    ui.alert('연결 성공',
      "통합 '" + self.integration + "'(워크스페이스: " + self.workspace + ")이 노션 데이터베이스 '" + title + "'에 연결되었습니다.\n" +
      '이제 [④ 자동 전송 켜기]를 실행하면 설치가 끝납니다.',
      ui.ButtonSet.OK);
  } catch (e2) {
    setStatus_(ss, '노션 연결', nowStamp_() + ' 실패(데이터베이스 접근 단계)');
    setStatus_(ss, '마지막 오류', nowStamp_() + ' ' + e2.message);
    ui.alert('연결 실패(데이터베이스 접근 단계)',
      '토큰 자체는 유효합니다.\n' +
      "· 통합 이름: " + self.integration + '\n' +
      "· 통합이 속한 워크스페이스: " + self.workspace + '\n\n' +
      '그런데 이 통합으로는 데이터베이스가 보이지 않습니다. 순서대로 확인해 주세요.\n\n' +
      "1) 연결 추가: 노션에서 '📋 주간·월간 업무 계획' 데이터베이스 페이지(또는 상위 '우리학교 교무실' 페이지)를 열고, " +
      "우측 상단 ⋯ 메뉴의 '연결(Connections)'에서 '" + self.integration + "'을 검색해 추가합니다. 토큰 입력과는 별개로 꼭 필요한 단계입니다.\n\n" +
      "2) 워크스페이스 일치: 학교 페이지가 있는 워크스페이스가 위의 '" + self.workspace + "'과 같은지 확인합니다. " +
      '다르면 통합을 학교 워크스페이스에서 새로 만들고 그 시크릿을 다시 입력해야 합니다.\n\n' +
      '확인 후 [③ 연결 테스트]를 다시 실행해 주세요.\n\n원래 오류: ' + e2.message,
      ui.ButtonSet.OK);
  }
}

/* =====================================================================
 * 10. 자동 트리거
 * =================================================================== */

var TRIGGER_HANDLERS = ['autoSyncDirty', 'dailyHousekeeping', 'onEditInstallable'];

function removeOurTriggers_() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (TRIGGER_HANDLERS.indexOf(t.getHandlerFunction()) >= 0) ScriptApp.deleteTrigger(t);
  });
}

function enableAutoSync() {
  var ss = SpreadsheetApp.getActive();
  var ui = SpreadsheetApp.getUi();
  try {
    getToken_();
    removeOurTriggers_();
    ScriptApp.newTrigger('onEditInstallable').forSpreadsheet(ss).onEdit().create();
    ScriptApp.newTrigger('autoSyncDirty').timeBased().everyMinutes(CONFIG.SYNC_EVERY_MINUTES).create();
    ScriptApp.newTrigger('dailyHousekeeping').timeBased().atHour(CONFIG.HOUSEKEEPING_HOUR).everyDays(1).inTimezone(CONFIG.TZ).create();
    ui.alert('자동 전송 켜짐',
      '이제 시트를 수정하면 ' + CONFIG.SYNC_EVERY_MINUTES + '분 안에 노션에 자동 반영됩니다.\n' +
      '매일 아침에는 설정에 따라 다음 주 탭과 다음 달 월간 탭이 자동 생성됩니다.',
      ui.ButtonSet.OK);
  } catch (e) {
    ui.alert('설정 실패', e.message, ui.ButtonSet.OK);
  }
}

function disableAutoSync() {
  removeOurTriggers_();
  SpreadsheetApp.getUi().alert('자동 전송 끔', '자동 전송과 자동 탭 생성을 모두 껐습니다. 수동 전송 메뉴는 계속 사용할 수 있습니다.', SpreadsheetApp.getUi().ButtonSet.OK);
}

function onEditInstallable(e) {
  try {
    var sheet = e && e.range ? e.range.getSheet() : null;
    if (!sheet) return;
    var type = sheetType_(sheet);
    if (type !== 'week' && type !== 'month') return;
    // 스크립트가 기록하는 상태 칸(G2/F2)의 수정은 무시
    PropertiesService.getScriptProperties().setProperty('dirty_' + sheet.getSheetId(), String(Date.now()));
  } catch (err) { /* 무시 */ }
}

function autoSyncDirty() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return;
  try {
    try { ensureDeptRowsOnce_(); } catch (eDept) { }
    try { migrateMonthTabsOnce_(); } catch (eMig) { }
    var sp = PropertiesService.getScriptProperties();
    var keys = sp.getKeys().filter(function (k) { return k.indexOf('dirty_') === 0; });
    var ss = SpreadsheetApp.getActive();
    if (!keys.length) {
      // 시트 수정이 없어도 학사일정 달력의 변경은 주기적으로 반영한다
      try { calendarWatch_(makeCtx_(ss)); } catch (eW) { }
      return;
    }
    var ctx = makeCtx_(ss);
    var byId = {};
    ss.getSheets().forEach(function (sh) { byId[String(sh.getSheetId())] = sh; });
    var months = {};
    var okCount = 0;
    keys.forEach(function (k) {
      var sheet = byId[k.slice('dirty_'.length)];
      sp.deleteProperty(k);
      if (!sheet) return;
      var type = sheetType_(sheet);
      try {
        if (type === 'week') {
          var r = syncWeeklySheet_(ctx, sheet);
          months[r.y + '-' + r.m] = { y: r.y, m: r.m };
          okCount++;
        } else if (type === 'month') {
          var p = parseIso(readAnchorIso_(ss, sheet));
          months[p.y + '-' + p.m] = { y: p.y, m: p.m };
          okCount++;
        }
      } catch (e1) {
        setStatus_(ss, '마지막 오류', nowStamp_() + " '" + sheet.getName() + "' " + e1.message);
      }
    });
    Object.keys(months).forEach(function (k) {
      try { syncMonth_(ctx, months[k].y, months[k].m); }
      catch (e2) { setStatus_(ss, '마지막 오류', nowStamp_() + ' 월간 갱신: ' + e2.message); }
    });
    if (okCount) setStatus_(ss, '마지막 자동 전송', nowStamp_());
    try { calendarWatch_(ctx); } catch (eW2) { }
  } catch (e) {
    try { setStatus_(SpreadsheetApp.getActive(), '마지막 오류', nowStamp_() + ' ' + e.message); } catch (ignore) {}
  } finally {
    lock.releaseLock();
  }
}

function dailyHousekeeping() {
  var ss = SpreadsheetApp.getActive();
  var st = getSettings_(ss);
  var today = todayIso_();
  var weekdayKo = ['일', '월', '화', '수', '목', '금', '토'][weekdayOf(today)];
  var created = false;

  // 이번 주 탭 보증
  var thisMonday = mondayOf(today);
  if (!findWeekSheet_(ss, thisMonday)) {
    createWeekTab_(ss, thisMonday);
    created = true;
  }
  // 다음 주 탭
  if (st.nextWeekDay !== '안 함' && weekdayKo === st.nextWeekDay) {
    var nextMonday = addDays(thisMonday, 7);
    if (!findWeekSheet_(ss, nextMonday)) {
      createWeekTab_(ss, nextMonday);
      created = true;
    }
  }
  // 다음 달 월간 탭
  var p = parseIso(today);
  if (st.nextMonthDate > 0 && p.d === st.nextMonthDate) {
    var ny = p.m === 12 ? p.y + 1 : p.y;
    var nm = p.m === 12 ? 1 : p.m + 1;
    if (!findMonthSheetByYm_(ss, ny, nm)) {
      createMonthTab_(ss, ny, nm, st.offset);
      created = true;
    }
  }
  if (created) {
    try {
      var ctx = makeCtx_(ss);
      // 새로 만든 탭의 빈 페이지도 노션에 미리 만들어 둔다
      ss.getSheets().forEach(function (sh) {
        var t = sheetType_(sh);
        if (t !== 'week') return;
        var mondayIso = mondayOf(readAnchorIso_(ss, sh));
        if (!findPageByKey_(ctx.dsId, 'W' + mondayIso)) syncWeeklySheet_(ctx, sh);
      });
    } catch (e) {
      setStatus_(ss, '마지막 오류', nowStamp_() + ' 자동 탭 생성 후 전송: ' + e.message);
    }
  }
}

/* =====================================================================
 * 11. 탭 생성
 * =================================================================== */

function findWeekSheet_(ss, mondayIso) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheetType_(sheets[i]) !== 'week') continue;
    try {
      if (mondayOf(readAnchorIso_(ss, sheets[i])) === mondayIso) return sheets[i];
    } catch (e) { /* 무시 */ }
  }
  return null;
}

function findMonthSheetByYm_(ss, y, m) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheetType_(sheets[i]) !== 'month') continue;
    try {
      var p = parseIso(readAnchorIso_(ss, sheets[i]));
      if (p.y === y && p.m === m) return sheets[i];
    } catch (e) { /* 무시 */ }
  }
  return null;
}

function weekTabName_(mondayIso, offset) {
  var wm = weekMonth(mondayIso, offset);
  var wi = weekIndex(mondayIso, offset);
  return wm.m + '월' + wi + '주(' + mdDot(mondayIso) + '~' + mdDot(addDays(mondayIso, 4)) + ')';
}

function createWeekTab_(ss, mondayIso) {
  var st = getSettings_(ss);
  var exists = findWeekSheet_(ss, mondayIso);
  if (exists) return exists;
  var tpl = ss.getSheetByName(CONFIG.TPL_WEEK);
  if (!tpl) {
    tpl = ss.insertSheet(CONFIG.TPL_WEEK);
    buildWeeklyTemplate_(tpl);
    tpl.hideSheet();
  }
  var name = weekTabName_(mondayIso, st.offset);
  if (ss.getSheetByName(name)) return ss.getSheetByName(name);
  var sh = tpl.copyTo(ss).setName(name);
  sh.showSheet();
  sh.getRange('B2').setValue(isoToSerial_(mondayIso));
  sh.setTabColor(CONFIG.WEEK_TAB_COLOR);
  ss.setActiveSheet(sh);
  ss.moveActiveSheet(1);
  return sh;
}

function createMonthTab_(ss, y, m, offset) {
  var exists = findMonthSheetByYm_(ss, y, m);
  if (exists) return exists;
  var tpl = ss.getSheetByName(CONFIG.TPL_MONTH);
  if (!tpl) {
    tpl = ss.insertSheet(CONFIG.TPL_MONTH);
    buildMonthlyTemplate_(tpl);
    tpl.hideSheet();
  }
  var name = m + '월 월간';
  if (ss.getSheetByName(name)) name = y + '년 ' + name;
  var sh = tpl.copyTo(ss).setName(name);
  sh.showSheet();
  sh.getRange('B2').setValue(isoToSerial_(isoOf(y, m, 1)));
  trimMonthCalendarRows_(sh, y, m);
  sh.setTabColor(CONFIG.MONTH_TAB_COLOR);
  ss.setActiveSheet(sh);
  ss.moveActiveSheet(Math.min(2, ss.getSheets().length));
  return sh;
}

function createNextWeekTabMenu() {
  var ss = SpreadsheetApp.getActive();
  var next = addDays(mondayOf(todayIso_()), 7);
  var sh = createWeekTab_(ss, next);
  SpreadsheetApp.getUi().alert('완료', "'" + sh.getName() + "' 탭을 준비했습니다.", SpreadsheetApp.getUi().ButtonSet.OK);
}

function createWeekTabPromptMenu() {
  var ui = SpreadsheetApp.getUi();
  var res = ui.prompt('특정 주 탭 만들기', '만들려는 주의 아무 날짜나 yyyy-mm-dd 형식으로 입력하세요. (예: 2026-09-14)', ui.ButtonSet.OK_CANCEL);
  if (res.getSelectedButton() !== ui.Button.OK) return;
  var p = parseIso(res.getResponseText());
  if (!p) { ui.alert('날짜 형식이 올바르지 않습니다. 예: 2026-09-14'); return; }
  var sh = createWeekTab_(SpreadsheetApp.getActive(), mondayOf(isoOf(p.y, p.m, p.d)));
  ui.alert('완료', "'" + sh.getName() + "' 탭을 준비했습니다.", ui.ButtonSet.OK);
}

function createNextMonthTabMenu() {
  var ss = SpreadsheetApp.getActive();
  var st = getSettings_(ss);
  var p = parseIso(todayIso_());
  var ny = p.m === 12 ? p.y + 1 : p.y;
  var nm = p.m === 12 ? 1 : p.m + 1;
  var sh = createMonthTab_(ss, ny, nm, st.offset);
  SpreadsheetApp.getUi().alert('완료', "'" + sh.getName() + "' 탭을 준비했습니다.", SpreadsheetApp.getUi().ButtonSet.OK);
}

/* =====================================================================
 * 12. 초기 설정: 탭·양식 만들기
 * =================================================================== */

/* 시트를 완전히 초기 상태로 되돌린다(병합·보호·유효성 검사 포함).
 * 이전 실행이 중간에 실패해서 반쯤 만들어진 시트도 안전하게 재생성된다. */
function resetSheet_(sh) {
  sh.getProtections(SpreadsheetApp.ProtectionType.RANGE).forEach(function (p) { p.remove(); });
  var full = sh.getRange(1, 1, sh.getMaxRows(), sh.getMaxColumns());
  full.breakApart();
  full.clearDataValidations();
  sh.clear();
}

function initializeAll() {
  var ss = SpreadsheetApp.getActive();
  var ui = SpreadsheetApp.getUi();
  ss.setSpreadsheetTimeZone(CONFIG.TZ);

  var settings = ss.getSheetByName(CONFIG.SETTINGS_SHEET);
  if (!settings) {
    settings = ss.insertSheet(CONFIG.SETTINGS_SHEET);
    buildSettingsSheet_(settings);
    settings.setTabColor('#999999');
  }
  // 템플릿은 실행할 때마다 기본 양식으로 다시 그린다(부서 행을 바꾼 경우에는
  // 초기 설정을 재실행하지 말고 템플릿 탭을 직접 수정·유지한다).
  var tplW = ss.getSheetByName(CONFIG.TPL_WEEK) || ss.insertSheet(CONFIG.TPL_WEEK);
  buildWeeklyTemplate_(tplW);
  if (!tplW.isSheetHidden()) tplW.hideSheet();
  var tplM = ss.getSheetByName(CONFIG.TPL_MONTH) || ss.insertSheet(CONFIG.TPL_MONTH);
  buildMonthlyTemplate_(tplM);
  if (!tplM.isSheetHidden()) tplM.hideSheet();

  var st = getSettings_(ss);
  var today = todayIso_();
  var thisMonday = mondayOf(today);
  createWeekTab_(ss, addDays(thisMonday, 7));
  createWeekTab_(ss, thisMonday);

  var p = parseIso(today);
  var remaining = weeksOfMonth(p.y, p.m, st.offset).filter(function (mon) { return toUtc(mon) >= toUtc(thisMonday); });
  if (remaining.length >= 2) createMonthTab_(ss, p.y, p.m, st.offset);
  var ny = p.m === 12 ? p.y + 1 : p.y;
  var nm = p.m === 12 ? 1 : p.m + 1;
  createMonthTab_(ss, ny, nm, st.offset);

  // 기본으로 생기는 빈 시트 제거
  ['Sheet1', '시트1'].forEach(function (n) {
    var sh = ss.getSheetByName(n);
    if (sh && ss.getSheets().length > 1 && sh.getLastRow() === 0 && sh.getLastColumn() === 0) {
      ss.deleteSheet(sh);
    }
  });

  ui.alert('초기 설정 완료',
    '탭과 양식을 만들었습니다.\n\n남은 순서:\n' +
    '1) [② 노션 토큰 설정]에 통합 시크릿 입력\n' +
    '2) 노션 데이터베이스 페이지 ⋯ → 연결에 통합 추가\n' +
    '3) [③ 연결 테스트] → [④ 자동 전송 켜기]',
    ui.ButtonSet.OK);
}

/* ---- 양식 그리기 ---- */

function buildWeeklyTemplate_(sh) {
  resetSheet_(sh);
  var widths = [110, 150, 150, 150, 150, 150, 125];
  widths.forEach(function (w, i) { sh.setColumnWidth(i + 1, w); });

  // 주의: A1을 B열 쪽으로 병합하면 '첫 열 고정'과 충돌해서 오류가 난다.
  // 병합 없이도 옆 칸이 비어 있으면 제목이 이어져 표시된다.
  sh.getRange('A1').setValue(CONFIG.WEEK_TITLE)
    .setFontSize(16).setFontWeight('bold').setFontColor('#1a3c6e');
  sh.getRange('F1:G1').merge();
  sh.getRange('F1').setFormula('=IF($B$2="","",MONTH($B$2+2)&"월 "&(INT((DAY($B$2+2)-1)/7)+1)&"주")')
    .setFontSize(13).setFontWeight('bold').setFontColor('#2e5fa3').setHorizontalAlignment('right');
  sh.setRowHeight(1, 32);

  sh.getRange('A2').setValue('기간(월요일)').setFontWeight('bold').setFontColor('#555555').setFontSize(10)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sh.getRange('B2').setNumberFormat('yyyy-mm-dd').setFontWeight('bold')
    .setHorizontalAlignment('center').setBackground('#fff6de');
  sh.getRange('C2:E2').merge();
  sh.getRange('C2').setFormula('=IF($B$2="","",TEXT($B$2,"m. d.")&"(월) ~ "&TEXT($B$2+4,"m. d.")&"(금)")')
    .setFontWeight('bold');
  sh.getRange('F2').setValue('노션 반영:').setFontColor('#888888').setFontSize(9).setHorizontalAlignment('right');
  sh.getRange('G2').setFontColor('#888888').setFontSize(9);
  sh.getRange('A2:B2').setBorder(true, true, true, true, true, true, '#b7b7b7', SpreadsheetApp.BorderStyle.SOLID);

  sh.getRange('A3:G3').setValues([['요일', '월', '화', '수', '목', '금', '토~일']]);
  sh.getRange('A4').setValue('부서');
  for (var i = 0; i < 5; i++) {
    sh.getRange(4, 2 + i).setFormula(i === 0 ? '=IF($B$2="","",$B$2)' : '=IF($B$2="","",$B$2+' + i + ')')
      .setNumberFormat('m/d');
  }
  sh.getRange('G4').setFormula('=IF($B$2="","",TEXT($B$2+5,"m/d")&"~"&TEXT($B$2+6,"m/d"))');
  sh.getRange('A3:G4').setBackground('#eff3f8').setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sh.setRowHeights(3, 2, 22);

  var n = CONFIG.DEPTS.length;
  for (var r = 0; r < n; r++) {
    sh.getRange(5 + r, 1).setValue(CONFIG.DEPTS[r]);
    sh.setRowHeight(5 + r, 88);
  }
  var noteRow = 5 + n;
  sh.getRange(noteRow, 1).setValue('전달,협의사항');
  sh.setRowHeight(noteRow, 66);
  sh.getRange(noteRow, 2, 1, 6).merge();

  sh.getRange(5, 1, n + 1, 1).setBackground('#f8f9fa').setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle').setWrap(true);
  sh.getRange(5, 2, n + 1, 6).setVerticalAlignment('top').setWrap(true);
  sh.getRange(3, 1, n + 2, 7).setBorder(true, true, true, true, true, true, '#b7b7b7', SpreadsheetApp.BorderStyle.SOLID);

  sh.getRange(noteRow + 2, 1)
    .setValue('◾ 사용법: 부서별로 해당 요일 칸에 업무를 입력하세요. 여러 항목은 줄바꿈(Alt+Enter)으로 구분합니다. 저장하면 ' +
      CONFIG.SYNC_EVERY_MINUTES + '분 안에 노션에 자동 반영되고, 반영 시각이 위 [노션 반영]에 표시됩니다.')
    .setFontColor('#888888').setFontSize(9);
  sh.setFrozenRows(4);
  sh.setFrozenColumns(1);
  var prot = sh.getRange('A1:G4').protect();
  prot.setWarningOnly(true);
}

function buildMonthlyTemplate_(sh) {
  resetSheet_(sh);
  for (var c0 = 1; c0 <= 7; c0++) sh.setColumnWidth(c0, 168);

  sh.getRange('A1').setValue(CONFIG.MONTH_TITLE)
    .setFontSize(16).setFontWeight('bold').setFontColor('#3d2a66');
  sh.getRange('F1:G1').merge();
  sh.getRange('F1').setFormula('=IF($B$2="","",YEAR($B$2)&"년 "&MONTH($B$2)&"월")')
    .setFontSize(13).setFontWeight('bold').setFontColor('#5b3e8e').setHorizontalAlignment('right');
  sh.setRowHeight(1, 32);

  sh.getRange('A2').setValue('대상 월(1일)').setFontWeight('bold').setFontColor('#555555').setFontSize(10)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sh.getRange('B2').setNumberFormat('yyyy-mm-dd').setFontWeight('bold')
    .setHorizontalAlignment('center').setBackground('#f3edfc');
  sh.getRange('F2').setValue('노션 반영:').setFontColor('#888888').setFontSize(9).setHorizontalAlignment('right');
  sh.getRange('G2').setFontColor('#888888').setFontSize(9);
  sh.getRange('A2:B2').setBorder(true, true, true, true, true, true, '#b7b7b7', SpreadsheetApp.BorderStyle.SOLID);

  sh.getRange(3, 1, 1, 7).setValues([CONFIG.CAL_DOW]);
  sh.getRange(3, 1, 1, 7).setBackground('#eff3f8').setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sh.setRowHeight(3, 26);
  sh.getRange(3, 1).setFontColor('#c0392b');
  sh.getRange(3, 7).setFontColor('#2a6099');

  var base = '$B$2-WEEKDAY($B$2)+1';
  for (var w = 0; w < CONFIG.CAL_WEEKS; w++) {
    var dRow = 4 + w * 2;
    var cRow = dRow + 1;
    for (var c = 0; c < 7; c++) {
      var off = w * 7 + c;
      var expr = base + (off ? '+' + off : '');
      sh.getRange(dRow, c + 1).setFormula(
        '=IF($B$2="","",IF(MONTH(' + expr + ')<>MONTH($B$2),"",DAY(' + expr + ')))');
    }
    sh.setRowHeight(dRow, 20);
    sh.setRowHeight(cRow, 74);
    sh.getRange(dRow, 1, 1, 7).setFontWeight('bold').setFontSize(9)
      .setHorizontalAlignment('left').setVerticalAlignment('middle').setBackground('#f5f6f8');
    sh.getRange(dRow, 1).setFontColor('#c0392b');
    sh.getRange(dRow, 7).setFontColor('#2a6099');
    sh.getRange(cRow, 1, 1, 7).setVerticalAlignment('top').setWrap(true).setFontSize(10);
  }

  var noteRow = 4 + CONFIG.CAL_WEEKS * 2;
  sh.getRange(noteRow, 1).setValue('월간 전달사항').setFontWeight('bold').setBackground('#f8f9fa')
    .setHorizontalAlignment('center').setVerticalAlignment('middle').setWrap(true);
  sh.getRange(noteRow, 2, 1, 6).merge();
  sh.getRange(noteRow, 2).setVerticalAlignment('top').setWrap(true);
  sh.setRowHeight(noteRow, 54);

  sh.getRange(3, 1, noteRow - 2, 7)
    .setBorder(true, true, true, true, true, true, '#b7b7b7', SpreadsheetApp.BorderStyle.SOLID);

  sh.getRange(noteRow + 2, 1)
    .setValue('◾ 날짜가 적힌 회색 줄 바로 아래 칸에 그 날의 행사를 적습니다. 여러 개는 줄바꿈(Alt+Enter)으로 나눕니다. ' +
      '노션 학사일정에서 내려온 일정에는 ' + CONFIG.CAL_MARKER.trim() + ' 표식이 붙고, ' +
      '표식 없이 적은 일정은 학사일정 달력에도 자동으로 등록됩니다.')
    .setFontColor('#888888').setFontSize(9);
  sh.setFrozenRows(3);
  var prot = sh.getRange('A1:G3').protect();
  prot.setWarningOnly(true);
}

function buildSettingsSheet_(sh) {
  sh.clear();
  [260, 340, 520].forEach(function (w, i) { sh.setColumnWidth(i + 1, w); });
  sh.getRange('A1').setValue('⚙️ 설정').setFontSize(14).setFontWeight('bold');
  sh.getRange('C1').setValue('B열의 값만 수정하세요. 나머지는 자동으로 관리됩니다.').setFontColor('#888888').setFontSize(9);

  var rows = [
    ['노션 데이터베이스 URL', CONFIG.DEFAULT_DB_URL, '자동 정리 결과가 쌓이는 노션 데이터베이스 주소입니다.'],
    ['주차의 소속 월 기준 요일', '수', "그 주의 이 요일이 속한 달을 '그 주의 달'로 봅니다. 예: 8/31(월)~9/4(금) 주는 수요일(9/2)이 9월이므로 '9월 1주'가 됩니다."],
    ['다음 주 탭 생성 요일', '월', "이 요일 아침(6~7시)에 다음 주 탭을 자동으로 만듭니다. '안 함'을 선택하면 만들지 않습니다."],
    ['다음 달 탭 생성일', 15, '매월 이 날짜 아침에 다음 달 월간 탭을 자동으로 만듭니다. 0이면 만들지 않습니다.'],
    ['요일별 보기 포함', '예', "노션 주간 페이지에 '요일별 한눈에 보기'(휴대전화에서 세로로 읽기 좋은 정리)를 함께 만듭니다."],
    ['대시보드 입력 비밀번호', '', '비워 두면 대시보드에서 비밀번호 없이 입력할 수 있습니다. 값을 넣으면 대시보드 저장 시 이 비밀번호를 요구합니다.'],
    ['학사일정 데이터베이스 URL', CONFIG.CAL_DB_URL_DEFAULT, "노션 학사일정 달력과 주간 탭 '주요일정' 행을 서로 동기화합니다. '사용 안 함'을 넣으면 끕니다."],
    ['학사일정 자동 등록', '예', "'주요일정' 행에 직접 적은 항목을 학사일정 달력에도 자동 등록합니다. 등록되면 📅 표식이 붙습니다."]
  ];
  sh.getRange(3, 1, rows.length, 3).setValues(rows);
  sh.getRange(3, 1, rows.length, 1).setFontWeight('bold');
  sh.getRange(3, 2, rows.length, 1).setBackground('#fff6de').setWrap(true);
  sh.getRange(3, 3, rows.length, 1).setFontColor('#888888').setFontSize(9).setWrap(true).setVerticalAlignment('top');
  sh.getRange(3, 1, rows.length, 2).setBorder(true, true, true, true, true, true, '#b7b7b7', SpreadsheetApp.BorderStyle.SOLID);
  for (var r = 3; r < 3 + rows.length; r++) sh.setRowHeight(r, 34);

  sh.getRange('B4').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(['월', '화', '수', '목', '금'], true).build());
  sh.getRange('B5').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(['월', '화', '수', '목', '금', '안 함'], true).build());
  sh.getRange('B7').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(['예', '아니오'], true).build());
  sh.getRange('B10').setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(['예', '아니오'], true).build());

  sh.getRange('A12').setValue('상태(자동 기록)').setFontSize(12).setFontWeight('bold');
  var statusRows = [['노션 연결', ''], ['마지막 자동 전송', ''], ['마지막 오류', '']];
  sh.getRange(13, 1, statusRows.length, 2).setValues(statusRows);
  sh.getRange(13, 1, statusRows.length, 1).setFontWeight('bold');
  sh.getRange(13, 1, statusRows.length, 2).setBorder(true, true, true, true, true, true, '#b7b7b7', SpreadsheetApp.BorderStyle.SOLID);

  sh.getRange('A17').setValue('🚀 설치 순서(최초 1회)').setFontSize(12).setFontWeight('bold');
  var steps = [
    '1. 확장 프로그램 → Apps Script에 Code.gs 내용을 붙여 넣고 저장합니다.',
    '2. 시트를 새로 고친 뒤 [📋 업무계획] 메뉴에서 [① 초기 설정]을 실행하고 권한을 승인합니다.',
    '3. notion.so/profile/integrations 에서 내부 통합을 만들고, 시크릿을 [② 노션 토큰 설정]에 붙여 넣습니다.',
    "4. 노션 '📋 주간·월간 업무 계획' 데이터베이스 페이지 ⋯ → 연결에 만든 통합을 추가합니다.",
    '5. [③ 연결 테스트] 확인 후 [④ 자동 전송 켜기]를 실행하면 설치가 끝납니다.'
  ];
  for (var s = 0; s < steps.length; s++) {
    sh.getRange(18 + s, 1).setValue(steps[s]);
    sh.getRange(18 + s, 1, 1, 3).merge();
  }
}

/* =====================================================================
 * 12-2. 학사일정 달력 ↔ 주간 탭 '주요일정' 행 동기화
 *
 *  원칙(순환 방지):
 *   - 학사일정의 원본은 노션 달력이다. 달력 일정은 시트에 '📅 ' 표식이 붙은
 *     줄로 내려오고, 이 줄들은 매 동기화 때 달력 내용으로 다시 그려진다.
 *     (📅 줄을 시트에서 고치거나 지워도 다음 동기화 때 달력 기준으로 복원된다)
 *   - 시트 '주요일정' 행에 표식 없이 직접 적은 줄은 달력에 자동 등록되고,
 *     등록된 뒤에는 📅 줄로 바뀐다. 따라서 같은 항목이 다시 등록되지 않는다.
 *   - 연속된 요일에 같은 문구를 적으면 하나의 기간 일정으로 묶어 등록한다.
 * =================================================================== */

function calSyncEnabled_(st) {
  var u = cellStr(st.calDbUrl);
  return !(u === '' || u === '사용 안 함' || u === '아니오' || u === '끄기');
}

function isCalLine(line) { return String(line || '').trim().indexOf('📅') === 0; }

function calLine(ev) {
  var s = CONFIG.CAL_MARKER + ev.name;
  if (ev.endIso && ev.endIso > ev.startIso) s += '(' + md(ev.startIso) + '~' + md(ev.endIso) + ')';
  return s;
}

/* 해당 날짜(들)를 포함하는 일정 목록 (순수) */
function calEventsForCol(events, colIdx, mondayIso) {
  var days = colIdx < 5 ? [addDays(mondayIso, colIdx)] : [addDays(mondayIso, 5), addDays(mondayIso, 6)];
  var out = [];
  events.forEach(function (ev) {
    var covers = days.some(function (d) { return ev.startIso <= d && d <= ev.endIso; });
    if (!covers) return;
    var dup = out.some(function (x) { return x.name === ev.name && x.startIso === ev.startIso; });
    if (!dup) out.push(ev);
  });
  return out;
}

/* 표식 없는 수동 입력 가운데 달력에 없는 항목을 등록 후보로 묶는다 (순수)
 * 반환: [{name, startIso, endIso, cols:[열 인덱스]}] */
function computeCalExports(cells, mondayIso, events) {
  var manualByCol = cells.map(function (c) {
    return splitLines(c).filter(function (l) { return !isCalLine(l); });
  });
  // 이미 달력에 있는 문구는 등록하지 않는다(그 줄은 📅 줄로 대체된다)
  function existsInCal(text, colIdx) {
    return calEventsForCol(events, colIdx, mondayIso).some(function (ev) {
      return ev.name.trim() === text.trim();
    });
  }
  var pending = {}; // text -> [colIdx...]
  for (var c = 0; c < 6; c++) {
    manualByCol[c].forEach(function (text) {
      if (existsInCal(text, c)) return;
      (pending[text] = pending[text] || []).push(c);
    });
  }
  var exports = [];
  Object.keys(pending).forEach(function (text) {
    var cols = pending[text].filter(function (v, i, a) { return a.indexOf(v) === i; }).sort(function (a, b) { return a - b; });
    var weekdayCols = cols.filter(function (c) { return c < 5; });
    var hasWeekend = cols.indexOf(5) >= 0;
    // 연속 요일 병합
    var run = [];
    for (var i = 0; i <= weekdayCols.length; i++) {
      var cur = weekdayCols[i];
      if (run.length && (i === weekdayCols.length || cur !== run[run.length - 1] + 1)) {
        exports.push({
          name: text,
          startIso: addDays(mondayIso, run[0]),
          endIso: addDays(mondayIso, run[run.length - 1]),
          cols: run.slice()
        });
        run = [];
      }
      if (i < weekdayCols.length) run.push(cur);
    }
    if (hasWeekend) {
      exports.push({ name: text, startIso: addDays(mondayIso, 5), endIso: addDays(mondayIso, 6), cols: [5] });
    }
  });
  return exports;
}

/* 최종 셀 내용(📅 줄 + 남겨 둘 수동 줄) 구성 (순수) */
function buildMajorCells(mondayIso, events, keepManual) {
  // keepManual: [{name, cols:[...]}] — 등록 실패했거나 자동 등록을 끈 항목
  var cells = [];
  for (var c = 0; c < 6; c++) {
    var lines = calEventsForCol(events, c, mondayIso).map(calLine);
    (keepManual || []).forEach(function (g) {
      if (g.cols.indexOf(c) >= 0) lines.push(g.name);
    });
    cells.push(lines.join('\n'));
  }
  return cells;
}

/* 노션 학사일정 조회: 주간과 겹치는 일정 목록 */
function queryCalendarEvents_(calDsId, fromIso, toIso) {
  var results = [];
  var cursor = null;
  do {
    var body = {
      filter: {
        and: [
          { property: '날짜', date: { on_or_after: addDays(fromIso, -62) } },
          { property: '날짜', date: { on_or_before: toIso } }
        ]
      },
      sorts: [{ property: '날짜', direction: 'ascending' }],
      page_size: 100
    };
    if (cursor) body.start_cursor = cursor;
    var out = notionFetch_('/v1/data_sources/' + calDsId + '/query', 'post', body);
    results = results.concat(out.results || []);
    cursor = out.has_more ? out.next_cursor : null;
  } while (cursor);

  var events = [];
  results.forEach(function (page) {
    var props = page.properties || {};
    var titleArr = (props['행사명'] && props['행사명'].title) || [];
    var name = titleArr.map(function (t) { return t.plain_text || ''; }).join('').trim();
    var dateObj = props['날짜'] && props['날짜'].date;
    if (!name || !dateObj || !dateObj.start) return;
    var startIso = String(dateObj.start).slice(0, 10);
    var endIso = String(dateObj.end || dateObj.start).slice(0, 10);
    if (endIso < fromIso || startIso > toIso) return;
    events.push({ name: name, startIso: startIso, endIso: endIso });
  });
  return events;
}

function createCalendarEvent_(calDsId, g) {
  var p = parseIso(g.startIso);
  var dateVal = { start: g.startIso };
  if (g.endIso && g.endIso > g.startIso) dateVal.end = g.endIso;
  notionFetch_('/v1/pages', 'post', {
    parent: { type: 'data_source_id', data_source_id: calDsId },
    properties: {
      '행사명': { title: rt(g.name) },
      '날짜': { date: dateVal },
      '구분': { select: { name: '학교행사' } },
      '월': { select: { name: p.m + '월' } },
      '메모': { rich_text: rt('주간 업무 계획에서 자동 등록') }
    }
  });
}

/* 주간 탭의 '주요일정' 행을 달력과 맞춘다. 내용이 바뀌었으면 true */
function refreshMajorScheduleRow_(ctx, sheet, mondayIso) {
  var st = ctx.settings;
  if (!calSyncEnabled_(st)) return false;
  var row = findDeptRowIndex_(sheet, CONFIG.MAJOR_ROW_NAME);
  if (row < 0) return false;

  var events;
  var calDsId;
  try {
    calDsId = getDataSourceId_(extractDbId_(st.calDbUrl));
    events = queryCalendarEvents_(calDsId, mondayIso, addDays(mondayIso, 6));
  } catch (e) {
    setStatus_(ctx.ss, '마지막 오류', nowStamp_() +
      ' 학사일정 접근 실패: ' + e.message +
      " (통합을 '우리학교 교무실' 상위 페이지에 연결하면 학사일정까지 접근됩니다)");
    return false;
  }

  var range = sheet.getRange(row, 2, 1, 6);
  var cells = range.getValues()[0].map(cellStr);
  var exports = computeCalExports(cells, mondayIso, events);
  var keepManual = [];
  exports.forEach(function (g) {
    if (!st.calPush) { keepManual.push(g); return; }
    try {
      createCalendarEvent_(calDsId, g);
      events.push({ name: g.name, startIso: g.startIso, endIso: g.endIso });
    } catch (e2) {
      keepManual.push(g);
      setStatus_(ctx.ss, '마지막 오류', nowStamp_() + " 학사일정 등록 실패('" + g.name + "'): " + e2.message);
    }
  });
  var newCells = buildMajorCells(mondayIso, events, keepManual);
  if (JSON.stringify(newCells) !== JSON.stringify(cells)) {
    range.setValues([newCells]);
    return true;
  }
  return false;
}

/* 자동 주기마다 이번 주·다음 주 탭을 달력과 대조하고, 바뀐 주만 노션에 재전송 */
/* 노션 학사일정 달력과 월중 행사 계획 탭의 양방향 동기화
 *  - 달력에 있는 일정은 표식이 붙은 줄로 내려오고, 매번 달력 기준으로 다시 그린다.
 *  - 표식 없이 적은 줄은 그 날짜의 학사일정으로 등록한 뒤 표식 줄로 바뀐다. */
/* 예전 '월간 업무 계획'(부서 x 주차) 탭을 '월중 행사 계획' 달력으로 바꾼다.
   부서별로 적혀 있던 사전 계획은 월간 전달사항 칸으로 옮겨 보관한다. */
/* 그 달에 하루도 걸치지 않는 주는 인쇄에서 빠지도록 줄을 숨긴다. */
function trimMonthCalendarRows_(sh, y, m) {
  var sun = calFirstSunday(y, m);
  var ym = isoOf(y, m, 1).slice(0, 7);
  for (var w = 0; w < CONFIG.CAL_WEEKS; w++) {
    var any = false;
    for (var c = 0; c < 7; c++) {
      if (addDays(sun, w * 7 + c).slice(0, 7) === ym) { any = true; break; }
    }
    var r = 4 + w * 2;
    if (any) sh.showRows(r, 2); else sh.hideRows(r, 2);
  }
}

function migrateMonthTabsToCalendar_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var done = [];
  ss.getSheets().forEach(function (sh) {
    var name = sh.getName();
    var isTpl = name === CONFIG.TPL_MONTH;
    if (!isTpl && sheetType_(sh) !== 'month') return;
    var grid = sh.getDataRange().getValues().map(function (row) {
      return row.map(function (v) { return v === null || v === undefined ? '' : String(v).trim(); });
    });
    if (calHeaderRow(grid) >= 0) return;
    var carried = [];
    var r0 = -1;
    for (var i = 0; i < grid.length; i++) { if (grid[i][0] === '부서') { r0 = i; break; } }
    var heads = r0 >= 0 ? grid[r0].slice(1, 6) : [];
    if (r0 >= 0) {
      for (var r = r0 + 1; r < grid.length; r++) {
        var label = grid[r][0];
        if (!label) break;
        if (label.replace(/\s/g, '').indexOf('월간전달') === 0) {
          splitLines(grid[r][1]).forEach(function (t) { carried.push(t); });
          break;
        }
        for (var c = 1; c <= 5; c++) {
          var txt = grid[r][c];
          if (!txt) continue;
          var head = oneLine(heads[c - 1] || (c + '주'));
          splitLines(txt).forEach(function (t) {
            carried.push('[' + oneLine(label) + ' / ' + head + '] ' + t);
          });
        }
      }
    }
    var anchor = sh.getRange('B2').getValue();
    buildMonthlyTemplate_(sh);
    if (anchor) {
      sh.getRange('B2').setValue(anchor);
      var pa = parseIso(sh.getRange('B2').getDisplayValue());
      if (pa) trimMonthCalendarRows_(sh, pa.y, pa.m);
    }
    if (carried.length) sh.getRange(4 + CONFIG.CAL_WEEKS * 2, 2).setValue(carried.join('\n'));
    if (isTpl) sh.hideSheet();
    done.push(name);
  });
  return done;
}

/* 달력으로 바꾸는 일은 한 번만 하면 되므로, 했는지 여부를 스크립트 속성에 적어 둔다. */
function migrateMonthTabsOnce_() {
  var sp = PropertiesService.getScriptProperties();
  if (sp.getProperty('monthCalendarV1')) return;
  var done = migrateMonthTabsToCalendar_();
  sp.setProperty('monthCalendarV1', String(Date.now()));
  if (done.length) {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    ss.getSheets().forEach(function (sh) {
      if (sheetType_(sh) === 'month') sp.setProperty('dirty_' + sh.getSheetId(), String(Date.now()));
    });
  }
}

/* 학교 홈페이지에 올릴 인쇄본을 A4 가로 한 장으로 내려받는 주소 */
function monthCalendarPdfUrl_(ss, sh) {
  return ss.getUrl().replace(/\/edit.*$/, '') +
    '/export?format=pdf&gid=' + sh.getSheetId() +
    '&portrait=false&size=A4&fitw=true&scale=4&sheetnames=false&printtitle=false' +
    '&pagenum=false&gridlines=false&fzr=false' +
    '&top_margin=0.35&bottom_margin=0.35&left_margin=0.3&right_margin=0.3';
}

function monthCalendarPdfMenu() {
  var ss = SpreadsheetApp.getActive();
  var ui = SpreadsheetApp.getUi();
  var sh = ss.getActiveSheet();
  if (sheetType_(sh) !== 'month') {
    var pt = parseIso(todayIso_());
    sh = findMonthSheetByYm_(ss, pt.y, pt.m);
    if (!sh) {
      ui.alert('월중 행사 계획 탭을 찾지 못했습니다. [다음 달 월간 탭 만들기]로 먼저 탭을 만들어 주세요.');
      return;
    }
  }
  var url = monthCalendarPdfUrl_(ss, sh);
  var html = HtmlService.createHtmlOutput(
    '<div style="font:13px/1.7 -apple-system,sans-serif;padding:8px 6px">' +
    '<p><b>' + sh.getName() + '</b> 탭을 A4 가로 한 장으로 내려받습니다.</p>' +
    '<p style="margin:14px 0"><a href="' + url + '" target="_blank" ' +
    'style="display:inline-block;padding:9px 16px;background:#3d2a66;color:#fff;' +
    'border-radius:6px;text-decoration:none">PDF 내려받기</a></p>' +
    '<p style="color:#777;margin:0">내려받은 파일을 학교 홈페이지에 그대로 올리시면 됩니다.</p></div>')
    .setWidth(400).setHeight(200);
  ui.showModalDialog(html, '월중 행사 계획 PDF');
}

/* 메뉴에서 직접 달력 양식을 다시 만들 때 쓴다. */
function rebuildMonthCalendarMenu() {
  var ui = SpreadsheetApp.getUi();
  PropertiesService.getScriptProperties().deleteProperty('monthCalendarV1');
  var done = migrateMonthTabsToCalendar_();
  ui.alert(done.length ? '달력 양식으로 바꾼 탭: ' + done.join(', ') : '이미 모든 월간 탭이 달력 양식입니다.');
}

function refreshMonthCalendarSheet_(ctx, sheet, y, m) {
  var st = ctx.settings;
  if (!calSyncEnabled_(st)) return false;
  var grid = normalizeGrid_(ctx.ss, sheet);
  var r0 = calHeaderRow(grid);
  if (r0 < 0) return false;

  var fromIso = isoOf(y, m, 1);
  var toIso = isoOf(y, m, lastDayOfMonth(y, m));
  var events, calDsId;
  try {
    calDsId = getDataSourceId_(extractDbId_(st.calDbUrl));
    events = queryCalendarEvents_(calDsId, fromIso, toIso);
  } catch (e) {
    setStatus_(ctx.ss, '마지막 오류', nowStamp_() +
      ' 학사일정 접근 실패: ' + e.message +
      " (통합을 '우리학교 교무실' 상위 페이지에 연결하면 학사일정까지 접근됩니다)");
    return false;
  }

  var sun = calFirstSunday(y, m);
  var ym = fromIso.slice(0, 7);
  var changed = false;
  for (var w = 0; w < CONFIG.CAL_WEEKS; w++) {
    var sheetRow = r0 + 3 + w * 2;
    if (sheetRow > sheet.getMaxRows()) break;
    var range = sheet.getRange(sheetRow, 1, 1, 7);
    var cells = range.getValues()[0].map(cellStr);
    var next = [];
    for (var c = 0; c < 7; c++) {
      var iso = addDays(sun, w * 7 + c);
      if (iso.slice(0, 7) !== ym) { next.push(cells[c]); continue; }
      next.push(calDayCellText_(ctx, calDsId, events, iso, cells[c], st.calPush));
    }
    if (next.join('|') !== cells.join('|')) {
      range.setValues([next]);
      changed = true;
    }
  }
  return changed;
}

/* 하루치 칸의 최종 문구를 만든다. 필요하면 학사일정에 새 일정을 등록한다. */
function calDayCellText_(ctx, calDsId, events, iso, cellText, push) {
  var dayEvents = events.filter(function (ev) { return ev.startIso <= iso && iso <= ev.endIso; });
  var keep = [];
  splitLines(cellText).forEach(function (line) {
    if (isCalLine(line)) return;
    var dup = dayEvents.some(function (ev) { return ev.name.trim() === line.trim(); });
    if (dup) return;
    if (!push) { keep.push(line); return; }
    try {
      createCalendarEvent_(calDsId, { name: line, startIso: iso, endIso: iso });
      var ev = { name: line, startIso: iso, endIso: iso };
      dayEvents.push(ev);
      events.push(ev);
    } catch (e) {
      keep.push(line);
      setStatus_(ctx.ss, '마지막 오류', nowStamp_() + " 학사일정 등록 실패('" + line + "'): " + e.message);
    }
  });
  var lines = [];
  dayEvents.forEach(function (ev) {
    var s = calLine(ev);
    if (lines.indexOf(s) < 0) lines.push(s);
  });
  return lines.concat(keep).join('\n');
}

function calendarWatch_(ctx) {
  if (!calSyncEnabled_(ctx.settings)) return;
  var thisMonday = mondayOf(todayIso_());
  var months = {};
  [thisMonday, addDays(thisMonday, 7)].forEach(function (mon) {
    var sheet = findWeekSheet_(ctx.ss, mon);
    if (!sheet) return;
    try {
      if (refreshMajorScheduleRow_(ctx, sheet, mon)) {
        var r = syncWeeklySheet_(ctx, sheet, true);
        months[r.y + '-' + r.m] = { y: r.y, m: r.m };
      }
    } catch (e) {
      setStatus_(ctx.ss, '마지막 오류', nowStamp_() + ' 학사일정 동기화: ' + e.message);
    }
  });
  var pNow = parseIso(todayIso_());
  var nY = pNow.m === 12 ? pNow.y + 1 : pNow.y;
  var nM = pNow.m === 12 ? 1 : pNow.m + 1;
  [{ y: pNow.y, m: pNow.m }, { y: nY, m: nM }].forEach(function (t) {
    var msh = findMonthSheetByYm_(ctx.ss, t.y, t.m);
    if (!msh) return;
    try {
      if (refreshMonthCalendarSheet_(ctx, msh, t.y, t.m)) months[t.y + '-' + t.m] = t;
    } catch (e3) {
      setStatus_(ctx.ss, '마지막 오류', nowStamp_() + ' 월중 행사 동기화: ' + e3.message);
    }
  });
  Object.keys(months).forEach(function (k) {
    try { syncMonth_(ctx, months[k].y, months[k].m); } catch (e2) { }
  });
}

/* =====================================================================
 * 13. 대시보드 웹 API
 *  - [배포 → 새 배포 → 웹 앱 / 실행: 나 / 액세스: 모든 사용자]로 배포한다.
 *  - GET  {exec}?api=dashboard  → 대시보드 데이터(JSON)
 *  - POST {exec}  본문(JSON):
 *      {action:'save', week:'this'|'next', dept:'부서명', day:0~5, text:'...', pin:''}
 *      {action:'saveNote', week:'this'|'next', text:'...', pin:''}
 *    응답: {ok, error?, data: 최신 대시보드 데이터}
 * =================================================================== */

/* 주간 페이로드 (순수 함수) */
function weekPayload(mondayIso, parsed, offset, extras) {
  var wm = weekMonth(mondayIso, offset);
  var wi = weekIndex(mondayIso, offset);
  var missing = [], filled = [];
  parsed.depts.forEach(function (d) {
    var has = d.days.some(function (t) { return String(t || '').trim(); });
    (has ? filled : missing).push(shortName(d.name));
  });
  return {
    mondayIso: mondayIso,
    label: wm.m + '월 ' + wi + '주',
    range: mdDot(mondayIso) + '.(월) ~ ' + mdDot(addDays(mondayIso, 4)) + '.(금)',
    dates: [0, 1, 2, 3, 4, 5, 6].map(function (i) { return addDays(mondayIso, i); }),
    depts: parsed.depts.map(function (d) {
      return { name: d.name, short: shortName(d.name), days: d.days };
    }),
    notes: parsed.notes || '',
    filled: filled,
    missing: missing,
    tabName: extras && extras.tabName || '',
    tabUrl: extras && extras.tabUrl || '',
    notionPageUrl: extras && extras.notionPageUrl || ''
  };
}

/* 월간 페이로드 (순수 함수) */
function monthPayload(y, m, cal, extras) {
  var sun = calFirstSunday(y, m);
  var ym = isoOf(y, m, 1).slice(0, 7);
  var rows = [], total = 0;
  for (var w = 0; w < CONFIG.CAL_WEEKS; w++) {
    var row = [], any = false;
    for (var c = 0; c < 7; c++) {
      var iso = addDays(sun, w * 7 + c);
      var inMonth = iso.slice(0, 7) === ym;
      if (inMonth) any = true;
      var items = inMonth ? ((cal && cal.days && cal.days[iso]) || []) : [];
      total += items.length;
      row.push({
        iso: iso,
        d: inMonth ? parseIso(iso).d : 0,
        items: items.map(function (t) { return String(t).replace(CONFIG.CAL_MARKER, ''); })
      });
    }
    if (any) rows.push(row);
  }
  return {
    y: y, m: m,
    label: y + '년 ' + m + '월',
    dow: CONFIG.CAL_DOW,
    weeks: rows,
    count: total,
    notes: cal ? cal.notes : '',
    tabUrl: extras && extras.tabUrl || '',
    notionPageUrl: extras && extras.notionPageUrl || ''
  };
}

function notionPageUrlFor_(key) {
  var id = PropertiesService.getScriptProperties().getProperty('NPAGE_' + key);
  return id ? 'https://www.notion.so/' + String(id).replace(/-/g, '') : '';
}

function buildDashboardData_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var st = getSettings_(ss);
  var off = st.offset;
  var today = todayIso_();
  var thisMonday = mondayOf(today);

  function weekOf(mondayIso) {
    var sh = findWeekSheet_(ss, mondayIso);
    if (!sh) return null;
    var parsed = parseWeeklyValues(normalizeGrid_(ss, sh));
    return weekPayload(mondayIso, parsed, off, {
      tabName: sh.getName(),
      tabUrl: sheetUrlOf_(ss, sh),
      notionPageUrl: notionPageUrlFor_('W' + mondayIso)
    });
  }

  function monthOf(y, m) {
    var sh = findMonthSheetByYm_(ss, y, m);
    if (!sh) return null;
    var cal = null;
    try { cal = parseMonthlyCalendar(normalizeGrid_(ss, sh), y, m); } catch (eCal) { }
    return monthPayload(y, m, cal, {
      tabUrl: sheetUrlOf_(ss, sh),
      notionPageUrl: notionPageUrlFor_('M' + y + '-' + pad2(m))
    });
  }

  var wmNow = weekMonth(thisMonday, off);
  var nextY = wmNow.m === 12 ? wmNow.y + 1 : wmNow.y;
  var nextM = wmNow.m === 12 ? 1 : wmNow.m + 1;
  var months = [];
  var m1 = monthOf(wmNow.y, wmNow.m);
  var m2 = monthOf(nextY, nextM);
  if (m1) months.push(m1);
  if (m2) months.push(m2);

  var calStatus = { enabled: false };
  if (calSyncEnabled_(st)) {
    try {
      getDataSourceId_(extractDbId_(st.calDbUrl));
      calStatus = { enabled: true, ok: true };
    } catch (eCal) {
      calStatus = { enabled: true, ok: false, error: eCal.message };
    }
  }

  return {
    ok: true,
    generatedAt: nowIsoDateTime_(),
    todayIso: today,
    pinRequired: !!st.dashPin,
    sheetUrl: ss.getUrl().split('#')[0],
    notionDbUrl: st.dbUrl,
    calendar: calStatus,
    thisWeek: weekOf(thisMonday),
    nextWeek: weekOf(addDays(thisMonday, 7)),
    months: months
  };
}

function jsonOut_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  try {
    var api = e && e.parameter && e.parameter.api;
    if (api === 'dashboard') return jsonOut_(buildDashboardData_());
    return jsonOut_({ ok: true, hint: '?api=dashboard 로 조회하고, 입력은 POST(JSON)로 전송합니다.' });
  } catch (err) {
    return jsonOut_({ ok: false, error: err.message });
  }
}

function doPost(e) {
  var out = { ok: false };
  var lock = LockService.getScriptLock();
  var locked = false;
  try {
    var req = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var st = getSettings_(ss);
    if (st.dashPin && String(req.pin || '') !== st.dashPin) {
      out.error = '입력 비밀번호가 올바르지 않습니다.';
      out.pinRequired = true;
      return jsonOut_(out);
    }
    locked = lock.tryLock(20000);
    if (!locked) throw new Error('다른 저장이 진행 중입니다. 잠시 후 다시 시도해 주세요.');
    if (req.action === 'save') handleSave_(ss, req);
    else if (req.action === 'saveNote') handleSaveNote_(ss, req);
    else throw new Error('알 수 없는 요청입니다: ' + req.action);
    out.ok = true;
  } catch (err) {
    out.error = err.message;
  } finally {
    if (locked) { try { lock.releaseLock(); } catch (x) { } }
  }
  try { out.data = buildDashboardData_(); } catch (e2) { }
  return jsonOut_(out);
}

function resolveWeekSheet_(ss, which) {
  var thisMonday = mondayOf(todayIso_());
  var mondayIso = which === 'next' ? addDays(thisMonday, 7) : thisMonday;
  var sh = findWeekSheet_(ss, mondayIso) || createWeekTab_(ss, mondayIso);
  return { sheet: sh, mondayIso: mondayIso };
}

/* '요일' 행 아래에서 부서 이름이 있는 1-기준 행 번호를 찾는다 */
function findDeptRowIndex_(sheet, deptName) {
  var vals = sheet.getRange('A1:A60').getValues();
  var start = -1;
  for (var i = 0; i < vals.length; i++) {
    if (cellStr(vals[i][0]) === '요일') { start = i + 2; break; }
  }
  if (start < 0) throw new Error('주간 탭의 양식을 인식하지 못했습니다.');
  for (var r = start; r < vals.length; r++) {
    var label = cellStr(vals[r][0]);
    if (!label) break;
    if (label.replace(/\s/g, '').indexOf('전달') === 0) break;
    if (oneLine(label) === oneLine(deptName) || shortName(label) === String(deptName).trim()) {
      return r + 1;
    }
  }
  return -1;
}

function findNoteRowIndex_(sheet) {
  var vals = sheet.getRange('A1:A60').getValues();
  for (var i = 0; i < vals.length; i++) {
    if (cellStr(vals[i][0]).replace(/\s/g, '').indexOf('전달') === 0) return i + 1;
  }
  return -1;
}

function handleSave_(ss, req) {
  var day = Number(req.day);
  if (!(day >= 0 && day <= 5)) throw new Error('요일 값이 올바르지 않습니다.');
  var rw = resolveWeekSheet_(ss, req.week === 'next' ? 'next' : 'this');
  var row = findDeptRowIndex_(rw.sheet, String(req.dept || ''));
  if (row < 0) throw new Error("부서 '" + req.dept + "'를 주간 탭에서 찾지 못했습니다.");
  rw.sheet.getRange(row, 2 + day).setValue(String(req.text == null ? '' : req.text));
  PropertiesService.getScriptProperties()
    .setProperty('dirty_' + rw.sheet.getSheetId(), String(Date.now()));
}

/* 이미 만들어 둔 탭에도 새로 늘어난 부서 줄을 넣어 준다.
   맨 아래 전달사항 줄 바로 위에 끼워 넣고, 서식은 바로 위 줄에서 가져온다. */
/* 부서 줄 추가는 한 번만 하면 되므로, 했는지 여부를 스크립트 속성에 적어 둔다. */
function ensureDeptRowsOnce_() {
  var sp = PropertiesService.getScriptProperties();
  if (sp.getProperty('deptRowsAdded2')) return;
  var made = ensureDeptRows();
  sp.setProperty('deptRowsAdded2', String(Date.now()));
  if (made && made.indexOf('/') >= 0) {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    ss.getSheets().forEach(function (sh) {
      var ty = sheetType_(sh);
      if (ty === 'week' || ty === 'month') sp.setProperty('dirty_' + sh.getSheetId(), String(Date.now()));
    });
  }
}

function ensureDeptRows() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var added = [];
  ss.getSheets().forEach(function (sh) {
    var type = sheetType_(sh);
    if (!(type === 'week' || (type === 'template' && sh.getName() === CONFIG.TPL_WEEK))) return;
    var vals = sh.getRange(1, 1, Math.min(60, sh.getMaxRows()), 1).getValues();
    var noteRow = -1, have = {};
    for (var i = 0; i < vals.length; i++) {
      var label = cellStr(vals[i][0]);
      if (!label) continue;
      have[label] = true;
      if (noteRow < 0 && label.replace(/\s/g, '').indexOf('전달') >= 0) noteRow = i + 1;
    }
    if (noteRow < 2) return;
    var w = Math.min(8, sh.getMaxColumns());
    CONFIG.DEPTS.forEach(function (name) {
      if (have[name]) return;
      sh.insertRowBefore(noteRow);
      sh.getRange(noteRow - 1, 1, 1, w).copyTo(sh.getRange(noteRow, 1, 1, w), { formatOnly: true });
      sh.getRange(noteRow, 1, 1, w).clearContent();
      sh.getRange(noteRow, 1).setValue(name);
      sh.setRowHeight(noteRow, sh.getRowHeight(noteRow - 1));
      added.push(sh.getName() + ' / ' + name);
      noteRow++;
    });
  });
  return added.length ? added.join(', ') : '더할 줄이 없습니다.';
}

function handleSaveNote_(ss, req) {
  var rw = resolveWeekSheet_(ss, req.week === 'next' ? 'next' : 'this');
  var row = findNoteRowIndex_(rw.sheet);
  if (row < 0) throw new Error('전달·협의사항 행을 찾지 못했습니다.');
  rw.sheet.getRange(row, 2).setValue(String(req.text == null ? '' : req.text));
  PropertiesService.getScriptProperties()
    .setProperty('dirty_' + rw.sheet.getSheetId(), String(Date.now()));
}

/* =====================================================================
 * 14. Node 테스트용 내보내기 (Apps Script에서는 무시됨)
 * =================================================================== */

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    CONFIG: CONFIG,
    pad2: pad2, isoOf: isoOf, parseIso: parseIso, addDays: addDays,
    weekdayOf: weekdayOf, mondayOf: mondayOf, lastDayOfMonth: lastDayOfMonth,
    md: md, mdDot: mdDot,
    weekMonth: weekMonth, weekIndex: weekIndex, weekLabel: weekLabel, weeksOfMonth: weeksOfMonth,
    parseWeeklyValues: parseWeeklyValues, parseMonthlyCalendar: parseMonthlyCalendar,
    calHeaderRow: calHeaderRow, calFirstSunday: calFirstSunday, calTableRows: calTableRows,
    chunkText: chunkText, rt: rt, shortName: shortName,
    buildWeeklyBlocks: buildWeeklyBlocks, buildMonthlyBlocks: buildMonthlyBlocks,
    markerBlocks: markerBlocks,
    weekPayload: weekPayload, monthPayload: monthPayload,
    isCalLine: isCalLine, calLine: calLine, calEventsForCol: calEventsForCol,
    computeCalExports: computeCalExports, buildMajorCells: buildMajorCells
  };
}
