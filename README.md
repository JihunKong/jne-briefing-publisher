# jne-briefing-publisher

전남미래국제고등학교 학사일정 브리핑을 매일 자동 발행합니다.

## 동작
GitHub Actions 스케줄러가 매일 두 차례 (06:00 KST, 13:00 KST) 노션 학사일정 + NEIS 시간표/급식을 가져와 HTML로 렌더링한 뒤 GitHub gist에 PATCH 합니다. 각 선생님 PC의 `학사일정브리핑.exe`는 이 gist를 받아 표시만 합니다.

## 필요한 Secrets
저장소 `Settings → Secrets and variables → Actions`에 등록:

| 이름 | 값 |
|---|---|
| `NOTION_TOKEN` | 노션 internal integration 토큰 |
| `NEIS_API_KEY` | NEIS Open API 키 |
| `GIST_TOKEN` | GitHub PAT (gist 권한만으로 충분) |
| `GIST_ID` | 발행 대상 gist ID |

## 수동 실행
`Actions` 탭 → `Publish briefing` → `Run workflow`.

## 60일 비활성 자동 비활성화
GitHub은 활동 없는 repo의 스케줄을 60일 후 비활성화합니다. 본 워크플로는 매주 1회 `last_run.txt`를 커밋해 활동을 유지합니다.
