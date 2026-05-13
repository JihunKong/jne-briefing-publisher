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
3. **New repository secret** 버튼으로 아래 4개를 차례로 등록:

| Name | Value |
|---|---|
| `NOTION_TOKEN` | `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` |
| `NEIS_API_KEY` | `bad69babd5034282a754c2b8b364ea53` |
| `GIST_TOKEN` | `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` |
| `GIST_ID` | `5f2999ecdffdd04dee273ad9431dc27b` |

---

## 3단계 — 로컬 코드 푸시

CMD/PowerShell에서:

```
cd C:\Onnuri\JNEMessenger\actions-publisher
git remote add origin https://github.com/JihunKong/jne-briefing-publisher.git
git push -u origin main
```

(repo 이름을 다르게 지었다면 위 URL을 그에 맞게 수정)

푸시할 때 GitHub 자격증명 창이 뜨면 사용자명 `JihunKong`, 비밀번호 자리에는 **repo 권한 PAT** 가 필요합니다. 위 `GIST_TOKEN`은 gist 전용이라 푸시에는 쓸 수 없습니다. 둘 중 하나:

- (a) https://github.com/settings/tokens/new 에서 **`repo`, `workflow` 권한**의 새 PAT 발급 → 그 값을 비밀번호 자리에 붙여넣기
- (b) GitHub Desktop 또는 VS Code Git 통합으로 푸시 (브라우저 OAuth로 인증)

---

## 4단계 — 수동 테스트

1. 푸시 후 repo 페이지의 **Actions** 탭으로 이동
2. 왼쪽 **Publish briefing** 워크플로 선택
3. 우측 **Run workflow** 드롭다운 → **Run workflow** 클릭
4. 1~2분 후 완료되면 로그에서 `gist 업로드 완료` 확인
5. 브라우저에서 https://gist.github.com/JihunKong/5f2999ecdffdd04dee273ad9431dc27b 열어 갱신 시각이 방금 시각인지 확인

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
