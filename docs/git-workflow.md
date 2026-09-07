# Git 작업 안내

## 기본 전략

`main`은 검증된 통합 기준입니다. 기능·버그·환경 변경은 짧게 유지하는 작업 브랜치에서
진행하고, 초안 PR을 만든 뒤 검증과 리뷰가 끝나면 GitHub에서 **Create a merge commit**으로
병합합니다. 고정된 `develop`·`release` 브랜치는 사용하지 않습니다.

기존 AGENTS.md 규칙에 따라 문서·설정만 변경하는 경우에는 현재 브랜치에서 자동 커밋·푸시할
수 있습니다. `main`에서의 직접 커밋도 이 범위에 한정합니다. 앱 소스는 작업 브랜치에서
사용자가 지정한 파일만 커밋합니다. AI가 이 도구를 사용해 앱 소스 커밋 권한을 임의로
확대할 수는 없습니다.

| 상황 | 브랜치 예시 | 완료 방법 |
| --- | --- | --- |
| 새 기능 | `feature/video-upload` | 테스트 → push → PR → merge |
| 일반 버그 | `fix/upload-timeout` | 회귀 테스트 → push → PR → merge |
| 긴급 수정 | `hotfix/login-error` | 최신 main에서 시작, 필요한 수정·검증 후 PR |
| 문서 | `docs/setup-guide` | 작업 브랜치 또는 문서 전용 직접 커밋 |
| 설정·개발 도구 | `chore/git-workflow` | 작업 브랜치 권장, 설정 전용 직접 커밋도 가능 |
| 앱 버전 확정 | main의 `v0.1.0` | 검증된 main에 annotated tag 생성 후 게시 |
| 개발환경 재사용 기준 | main의 `dev-env-v1.1.0` | 환경 검증 후 새 annotated tag 생성·게시 |

기존 `dev-env-v1.0.0`은 최초 개발환경 기준으로 유지합니다. 이번 npm Git 도구는 그 태그
이후 변경입니다. 새 도구까지 포함한 기준이 필요하면 PR 병합·검증 후 새 환경 태그를 만듭니다.

## 메뉴로 실행

저장소 루트에서 다음 명령을 실행합니다. Node.js 22+, npm 9+, Git이 필요하며,
PR 생성에는 GitHub CLI(`gh`)와 해당 GitHub 저장소 인증이 추가로 필요합니다.
현재 Dev Container에는 이 도구들이 설치되어 있습니다. npm 외부 의존성은 없습니다.

```bash
npm run git
```

메뉴에서 작업을 고르고 필요한 이름·메시지·파일을 입력하면 실행할 명령이 표시됩니다.
`y`로 적용하고, Enter 또는 `n`으로 취소합니다. 자동 실행에서는 모든 입력과 `--yes`를
명시해야 합니다. `--dry-run`은 변경 없이 계획을 보여주며, 실제 실행 시에는 원격 상태를
다시 확인합니다. 잘못된 옵션이나 불충분한 입력은 작업을 실행하지 않습니다.

## 상황별 명령

| 명령 | 용도 |
| --- | --- |
| `npm run git:status` | 브랜치, 변경 파일, 로컬에 저장된 원격과의 차이 확인 |
| `npm run git:start` | 깨끗한 main을 최신화한 뒤 작업 브랜치 생성 |
| `npm run git:commit` | 파일 번호를 선택해서 커밋 |
| `npm run git:sync` | 현재 브랜치의 같은 이름 원격 브랜치와 fast-forward 동기화 |
| `npm run git:push` | 현재 브랜치 하나만 origin에 푸시하고 추적 설정 |
| `npm run git:pr` | 현재 원격 작업 브랜치에서 main으로 초안 PR 생성 |
| `npm run git:main` | 작업 브랜치를 보존하고 main으로 돌아가 동기화 |
| `npm run git:tag` | 원격과 일치하는 깨끗한 main에 설명 있는 로컬 태그 생성 |
| `npm run git:tag:push` | 지정한 annotated tag 하나만 원격에 게시 |
| `npm run git:help` | 직접 실행 옵션과 예시 |

새 기능을 시작하는 예시입니다. 작업 이름은 소문자·숫자·하이픈을 사용합니다.

```bash
npm run git:main -- --yes
npm run git:start -- --type feature --name video-upload --dry-run
npm run git:start -- --type feature --name video-upload --yes
```

구현 후 관련 테스트를 실행하고, 커밋할 파일을 선택합니다. 다음 경로는 사용 예시이며
실제로 변경한 파일을 지정해야 합니다. 경로는 저장소 루트 기준입니다.

```bash
npm run git:commit -- --message "feat: add video upload" --file lib/main.dart --dry-run
npm run git:commit -- --message "feat: add video upload" --file lib/main.dart --yes
npm run git:push -- --yes
npm run git:pr
```

긴 PR 본문은 직접 작성한 파일을 `--body-file`로 전달합니다. 변경 결과와 검증 내용을
적습니다. 실행 도구는 본문을 출력하고, GitHub CLI에 임시 파일로 전달한 뒤 정리합니다.

```bash
npm run git:pr -- --title "Add video upload" --body-file /tmp/pr-body.md --yes
```

PR 병합은 GitHub에서 수행합니다. 도구는 자동 병합이나 브랜치 삭제를 하지 않습니다.
병합 뒤 다음 작업을 시작하려면 `npm run git:main`으로 돌아갑니다.

## 커밋과 동기화 동작

- 선택한 파일의 현재 작업 내용을 커밋합니다. 파일 내부에서 일부만 스테이징한 경우에도
  그 파일을 선택하면 현재 파일 전체 내용이 대상입니다. 부분 커밋은 직접 Git으로 수행합니다.
- 다른 파일의 변경과 스테이징은 유지합니다. 새 파일·수정·삭제 파일을 선택할 수 있습니다.
  이름 변경은 삭제·추가 두 항목으로 표시되므로 두 항목을 함께 선택합니다.
- `main`의 직접 커밋은 `AGENTS.md`, `README.md`, `docs/**`, `.devcontainer/**`, 그리고
  도구에 명시된 설정 파일에 한정합니다. 인식하지 못하는 설정은 작업 브랜치로 진행합니다.
  전체 허용 목록은 `.devcontainer/scripts/git-workflow-core.mjs`의 `CONFIG_FILES`에 있습니다.
- `main` 직접 푸시도 원격에 없는 각 커밋의 파일을 검사합니다. 앱 소스 수정 후 다시
  원복해서 최종 차이를 없앤 경우에도 PR 경로를 사용해야 합니다.
- 새 브랜치 시작·main 복귀·동기화·태그 작업은 깨끗한 작업 트리에서 수행합니다.
  충돌·merge·rebase 등이 진행 중이면 해당 작업을 먼저 직접 완료합니다.
- 동기화는 fast-forward만 사용합니다. 로컬과 원격이 갈라지면 자동으로 rebase하거나
  reset하지 않고 중단합니다. `git status`와 이력을 검토하고 직접 merge로 해결합니다.
- 새 작업 브랜치는 자동으로 main을 추적하지 않습니다. 첫 push 후 같은 이름의
  `origin/<branch>`를 추적합니다. PR을 만들기 전에는 변경 내용을 커밋·푸시해야 합니다.

이 검사는 npm 도구를 통해 실행할 때 적용됩니다. GitHub 저장소의 서버 측 branch protection
설정을 변경하지는 않습니다.

## 태그와 복구

태그 생성과 원격 게시를 분리합니다. 기존 태그는 이동하거나 덮어쓰지 않습니다.

```bash
npm run git:main -- --yes
npm run git:tag -- --name dev-env-v1.1.0 --message "Updated development baseline" --yes
npm run git:tag:push -- --name dev-env-v1.1.0 --yes
```

앱 버전은 `v<major>.<minor>.<patch>`, 환경 기준은 `dev-env-v<major>.<minor>.<patch>`를
사용합니다. 앱 버전 태그는 `pubspec.yaml`의 앱 버전과 맞추고, 버전 파일 수정과 검증은
태그 생성 전에 완료합니다. 도구가 버전을 자동으로 변경하지는 않습니다.

잘못된 커밋은 새 수정 커밋 또는 `git revert`로 복구합니다. reset, amend, rebase,
force-push로 공유 이력을 바꾸지 않습니다. 복잡한 merge의 revert는 대상과 영향을
검토한 뒤 직접 수행합니다.

## 검증

```bash
npm run test:git
```

Git 도구 테스트는 임시 저장소와 로컬 bare 원격을 사용합니다. 실제 GitHub 저장소에
테스트 커밋·태그·PR을 게시하지 않습니다. 앱이나 backend를 변경했을 때는 별도로 관련
Flutter·Python 테스트를 실행해야 합니다.

참고: [GitHub flow](https://docs.github.com/en/get-started/using-github/github-flow),
[선택 경로만 커밋](https://git-scm.com/docs/git-commit),
[fast-forward 병합](https://git-scm.com/docs/git-merge),
[GitHub CLI PR 생성](https://cli.github.com/manual/gh_pr_create).
