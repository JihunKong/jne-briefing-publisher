# GitHub Actions 마이그레이션 절차

공지훈 선생님 PC 의존성을 없애고 GitHub 서버에서 자동 발행하도록 옮기는 1회성 셋업 절차입니다.

---

## 1단계 — GitHub에서 새 repo 만들기

1. https://github.com/new 접속
2. **Repository name**: `jne-briefing-publisher` (이름은 자유)
3. **Private** 선택 (월 2000분 무료 한도 충분)
4. **Add a README**, **.gitignore**, **license** 모두 **체크 해제** (이미 로컬에 있음)
5. **Create repository** 클릭

---

## 2단계 — Secrets 등록

방금 만든 repo 페이지에서:

1. 상단 메뉴 **Settings** 클릭
2. 왼쪽 사이드바 **Secrets and variables → Actions** 클릭
3. **New repository secret** 버튼으로 아래 항목을 차례로 등록:

> ⚠️ 값은 이 문서에 적지 않습니다. 아래 표의 '가져오는 곳'에서 직접 복사해 GitHub Secrets 화면에만 붙여 넣으세요.
> Secrets에 등록한 값은 화면에 다시 표시되지 않으므로, 필요하면 발급처에서 새로 발급받아 갱신합니다.

| Name | 가져오는 곳 |
|---|---|
| `NOTION_TOKEN` | notion.so/profile/integrations 에서 학사일정 데이터베이스에 연결한 내부 통합의 시크릿 |
| `NEIS_API_KEY` | open.neis.go.kr 에서 발급받은 NEIS Open API 인증키 |
| `GIST_TOKEN` | github.com/settings/tokens 에서 발급한 PAT(gist 권한만 있으면 충분합니다) |
| `GIST_ID` | 발행 대상 gist 주소의 마지막 식별자 |
| `WORKPLAN_API_URL` | 주간 업무 계획 Apps Script 웹 앱의 `/exec` 주소 |

---

## 3단계 — 로컬 코드 푸시

CMD/PowerShell에서:

```
cd C:\Onnuri\JNEMessenger\actions-publisher
git remote add origin https://github.com/JihunKong/jne-briefing-publisher.git
git push -u origin main
```

(repo 이름을 다르게 지었다면 위 URL을 그에 맞게 수정)

푸시할 때 GitHub 자격증명 창이 뜨면 사용자명 `JihunKong`, 비밀번호 자리에는 **repo 권한 PAT** 가 필요합니다. `GIST_TOKEN`으로 쓰는 PAT는 gist 전용 권한이라 푸시에는 사용할 수 없습니다. 둘 중 하나:

- (a) https://github.com/settings/tokens/new 에서 **`repo`, `workflow` 권한**의 새 PAT 발급 → 그 값을 비밀번호 자리에 붙여넣기
- (b) GitHub Desktop 또는 VS Code Git 통합으로 푸시 (브라우저 OAuth로 인증)

---

## 4단계 — 수동 테스트

1. 푸시 후 repo 페이지의 **Actions** 탭으로 이동
2. 왼쪽 **Publish briefing** 워크플로 선택
3. 우측 **Run workflow** 드롭다운 → **Run workflow** 클릭
4. 1~2분 후 완료되면 로그에서 `gist 업로드 완료` 확인
5. 브라우저에서 발행 대상 gist(`https://gist.github.com/{계정}/{GIST_ID}`)를 열어 갱신 시각이 방금 시각인지 확인

---

## 5단계 — 공지훈 PC의 기존 스케줄 끄기

GitHub Actions가 정상 동작 확인되면, 공지훈 PC에서:

```
schtasks /Change /TN JNE_Briefing_Publish /Disable
```

(완전 삭제하지 않고 일단 Disable만 — 문제 생기면 되살리기 위해)

---

## 동작 정리

- 매일 **06:00 KST**: 새 브리핑 발행 (선생님들 출근 8:30 전에 준비 완료)
- 매일 **13:00 KST**: 점심 무렵 한 번 더 갱신
- 수동 발행이 필요하면 Actions 탭에서 **Run workflow** 클릭
- 공지훈 선생님 PC가 켜져 있든 꺼져 있든 무관하게 정상 동작

---

## 자격 증명 관리 원칙

키와 토큰의 실제 값은 저장소 안의 어떤 파일에도 적지 않습니다. 값은 GitHub Actions Secrets에만 보관하고, 워크플로가 실행될 때 환경 변수로 주입합니다. `briefing_publish.py`와 `workplan_publish.py`는 `os.environ`에서만 값을 읽으므로, 문서에 값이 적혀 있는지 여부는 동작에 영향을 주지 않습니다.

한 번이라도 저장소에 값을 적어서 커밋했다면, 파일에서 지우더라도 커밋 기록에는 그대로 남습니다. 따라서 해당 키와 토큰은 발급처에서 폐기하고 새로 발급받은 뒤, GitHub Secrets의 값만 갱신해야 합니다. Secrets를 갱신하면 다음 실행부터 새 값이 적용되므로 발행은 중단 없이 이어집니다.
