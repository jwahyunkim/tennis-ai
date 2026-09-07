#!/usr/bin/env node

import { readFile } from 'node:fs/promises';
import { createInterface } from 'node:readline/promises';
import { parseArgs } from 'node:util';
import { GitWorkflow } from './git-workflow-core.mjs';

const help = `Git 전략: main + 작업 브랜치 + PR

  npm run git                 상황별 선택 메뉴
  npm run git:status          현재 브랜치와 변경 파일 확인
  npm run git:start           main에서 새 작업 브랜치 시작
  npm run git:commit          선택한 파일만 커밋
  npm run git:sync            현재 브랜치를 원격과 fast-forward 동기화
  npm run git:main            작업을 보존하고 main으로 돌아가 동기화
  npm run git:push            현재 브랜치만 원격에 푸시
  npm run git:pr              main으로 보내는 초안 PR 생성
  npm run git:tag             동기화된 main에 설명 있는 태그 생성
  npm run git:tag:push        선택한 태그 하나만 원격에 푸시

직접 실행 예시:
  npm run git:start -- --type feature --name video-upload --dry-run
  npm run git:start -- --type feature --name video-upload --yes
  npm run git:commit -- --message "feat: add video upload" --file lib/main.dart --yes
  npm run git:push -- --yes
  npm run git:pr -- --title "Add video upload" --body-file /tmp/pr-body.md --yes
  npm run git:tag -- --name dev-env-v1.1.0 --message "Updated development baseline" --yes
  npm run git:tag:push -- --name dev-env-v1.1.0 --yes

옵션:
  --dry-run     변경하지 않고 실행 계획만 표시
  --yes         입력한 작업을 확인 질문 없이 실행
  --file PATH   커밋할 파일; 여러 번 지정 가능, 경로는 저장소 루트 기준
  --help        도움말

main에는 문서·설정만 직접 커밋할 수 있습니다. 앱 소스는 작업 브랜치에서
파일을 명시적으로 선택해 커밋합니다. 푸시와 PR 생성은 별도 작업입니다.
자세한 전략: docs/git-workflow.md
`;

const actions = [
  ['status', '현재 상태 확인'],
  ['start', '새 작업 시작 (기능·수정·문서·설정)'],
  ['commit', '선택한 파일만 커밋'],
  ['sync', '현재 브랜치 동기화'],
  ['push', '현재 브랜치 푸시'],
  ['pr', '초안 PR 생성'],
  ['tag', '현재 main 커밋에 태그 생성'],
  ['publish-tag', '태그 하나를 원격에 푸시'],
  ['main', 'main으로 돌아가 동기화'],
];

const types = [
  ['feature', '새 기능'],
  ['fix', '일반 버그 수정'],
  ['hotfix', '긴급 수정'],
  ['docs', '문서 수정'],
  ['chore', '개발환경·설정·도구 변경'],
];

const optionsByAction = {
  status: [],
  start: ['type', 'name'],
  commit: ['message', 'file'],
  sync: [],
  main: [],
  push: [],
  pr: ['title', 'body-file'],
  tag: ['name', 'message'],
  'publish-tag': ['name'],
};

function showStatus(snapshot) {
  console.log(`\n브랜치: ${snapshot.branch || '(detached HEAD)'}`);
  console.log(`추적 원격: ${snapshot.upstream || '(없음)'}`);
  if (snapshot.upstream) {
    console.log(`로컬 기준: 앞선 커밋 ${snapshot.ahead}, 뒤처진 커밋 ${snapshot.behind}`);
  }
  if (!snapshot.changes.length) {
    console.log('변경 파일 없음');
  }
  snapshot.changes.forEach((change, index) => {
    const rename = change.originalPath ? `${JSON.stringify(change.originalPath)} → ` : '';
    console.log(`${index + 1}. [${change.status}] ${rename}${JSON.stringify(change.path)}`);
  });
}

function quoteArgument(argument) {
  return /^[a-zA-Z0-9_./:@=+-]+$/.test(argument)
    ? argument
    : `'${argument.replaceAll("'", "'\\''")}'`;
}

async function main() {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      help: { type: 'boolean' },
      yes: { type: 'boolean' },
      'dry-run': { type: 'boolean' },
      type: { type: 'string' },
      name: { type: 'string' },
      message: { type: 'string' },
      title: { type: 'string' },
      'body-file': { type: 'string' },
      file: { type: 'string', multiple: true },
    },
  });
  if (values.help) {
    console.log(help);
    return;
  }
  if (positionals.length > 1) {
    throw new Error('작업은 하나만 지정하세요. npm run git:help에서 사용법을 확인할 수 있습니다.');
  }
  if (values.yes && values['dry-run']) {
    throw new Error('--yes와 --dry-run 중 하나만 지정하세요.');
  }

  const interactive = Boolean(process.stdin.isTTY && process.stdout.isTTY);
  const terminal = interactive ? createInterface({ input: process.stdin, output: process.stdout }) : null;
  async function ask(prompt, required = true) {
    if (!terminal) {
      throw new Error('입력이 필요합니다. 터미널에서 실행하거나 도움말의 명시적 옵션을 사용하세요.');
    }
    const answer = (await terminal.question(prompt)).trim();
    if (required && !answer) throw new Error('입력값이 비어 있어 작업을 취소했습니다.');
    return answer;
  }
  async function choose(items, title) {
    console.log(`\n${title}`);
    items.forEach(([, label], index) => console.log(`${index + 1}. ${label}`));
    console.log('0. 종료');
    const answer = await ask('번호 선택: ');
    if (answer === '0') return null;
    if (!/^[1-9]\d*$/.test(answer) || Number(answer) > items.length) {
      throw new Error('목록에 있는 번호를 선택하세요.');
    }
    return items[Number(answer) - 1][0];
  }
  try {
    let action = positionals[0];
    if (!action) {
      if (!interactive) {
        if (Object.keys(values).length) {
          throw new Error('메뉴는 터미널에서 실행하세요. 자동 실행 시 작업명과 옵션을 명시하세요.');
        }
        console.log(help);
        return;
      }
      showStatus(new GitWorkflow().inspect());
      action = await choose(actions, '상황에 맞는 Git 작업을 선택하세요.');
      if (!action) return;
    }
    if (!Object.hasOwn(optionsByAction, action)) {
      throw new Error(`알 수 없는 작업: ${action}. npm run git:help를 확인하세요.`);
    }
    for (const key of Object.keys(values)) {
      if (!['yes', 'dry-run'].includes(key) && !optionsByAction[action].includes(key)) {
        throw new Error(`${action} 작업에는 --${key} 옵션을 사용할 수 없습니다.`);
      }
    }
    if (action === 'status') {
      showStatus(new GitWorkflow().status());
      return;
    }

    let args = [];
    let method = action;
    switch (action) {
      case 'start': {
        const type = values.type || await choose(types, '작업 종류');
        if (!type) return;
        args = [type, values.name || await ask('짧은 영문 작업명 (예: video-upload): ')];
        break;
      }
      case 'commit': {
        let paths = values.file;
        if (!paths?.length) {
          const snapshot = new GitWorkflow().inspect();
          showStatus(snapshot);
          if (!snapshot.changes.length) throw new Error('커밋할 변경 파일이 없습니다.');
          const selection = (await ask('커밋할 파일 번호 (예: 1,3): ')).split(/[\s,]+/);
          if (selection.some((value) => !/^[1-9]\d*$/.test(value) || Number(value) > snapshot.changes.length)) {
            throw new Error('변경 목록에 있는 파일 번호만 지정하세요.');
          }
          paths = [...new Set(selection.flatMap((number) => {
            const change = snapshot.changes[Number(number) - 1];
            return change.originalPath ? [change.originalPath, change.path] : [change.path];
          }))];
        }
        args = [values.message || await ask('커밋 메시지 (예: feat: add video upload): '), paths];
        break;
      }
      case 'pr': {
        const title = values.title || await ask('PR 제목: ');
        const body = values['body-file']
          ? await readFile(values['body-file'], 'utf8')
          : await ask('변경 내용과 검증 결과 (긴 본문은 --body-file 사용): ');
        console.log(`\nPR 제목: ${title}\nPR 본문:\n${body}`);
        args = [title, body];
        break;
      }
      case 'tag':
        args = [
          values.name || await ask('태그명 (예: v0.1.0 또는 dev-env-v1.1.0): '),
          values.message || await ask('태그 설명: '),
        ];
        break;
      case 'publish-tag':
        method = 'publishTag';
        args = [values.name || await ask('원격에 올릴 기존 태그명: ')];
        break;
      case 'main':
        method = 'backToMain';
        break;
    }

    const before = new GitWorkflow().inspect();
    const plan = new GitWorkflow({ dryRun: true })[method](...args);
    console.log(`\n대상 저장소: ${before.root}\n현재 브랜치: ${before.branch}`);
    console.log('\n실행 계획 (원격 상태는 실행 직전에 다시 확인합니다):');
    for (const command of plan.commands) {
      console.log(`  ${command.command} ${command.args.map(quoteArgument).join(' ')}`);
    }
    if (plan.existing) {
      console.log(`이미 열린 PR: ${plan.url}`);
      return;
    }
    if (values['dry-run']) {
      console.log('미리보기 완료. Git 이력과 작업 파일은 변경하지 않았습니다.');
      return;
    }
    if (!values.yes) {
      if (!interactive) throw new Error('실행하려면 --yes, 계획만 보려면 --dry-run을 지정하세요.');
      if (!/^(y|yes)$/i.test(await ask('위 작업을 실행할까요? [y/N]: ', false))) {
        console.log('취소했습니다.');
        return;
      }
    }
    const current = new GitWorkflow().inspect();
    if (current.branch !== before.branch || current.head !== before.head) {
      throw new Error('계획을 확인하는 동안 브랜치나 HEAD가 바뀌었습니다. 현재 상태를 확인하고 다시 실행하세요.');
    }
    const result = new GitWorkflow()[method](...args);
    if (result.output) console.log(result.output.trim());
    if (result.url && !result.output?.includes(result.url)) console.log(result.url);
    console.log('완료했습니다.');
  } finally {
    terminal?.close();
  }
}

main().catch((error) => {
  console.error(`오류: ${error.message}`);
  process.exitCode = 1;
});
