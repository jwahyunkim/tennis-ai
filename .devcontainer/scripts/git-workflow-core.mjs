import { spawnSync } from 'node:child_process';
import { existsSync, lstatSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { isAbsolute, join, resolve } from 'node:path';

export const BRANCH_TYPES = ['feature', 'fix', 'hotfix', 'docs', 'chore'];

const CONFIG_FILES = new Set([
  'AGENTS.md', 'README.md', '.editorconfig', '.gitignore', '.dockerignore',
  '.gitattributes', '.metadata', 'package.json', 'package-lock.json',
  'pubspec.yaml', 'pubspec.lock', 'analysis_options.yaml',
  'backend/requirements.in', 'backend/requirements.txt',
  'backend/requirements-dev.in', 'backend/requirements-dev.txt',
  'backend/pyproject.toml', 'backend/alembic.ini',
  'infra/compose.yaml', 'infra/.env.example',
  'android/.gitignore', 'android/build.gradle.kts',
  'android/settings.gradle.kts', 'android/gradle.properties',
  'android/app/build.gradle.kts', 'android/gradle/wrapper/gradle-wrapper.properties',
]);

export function isDocumentationOrConfig(path) {
  return CONFIG_FILES.has(path) || path.startsWith('docs/') || path.startsWith('.devcontainer/');
}

export class GitWorkflow {
  constructor({ cwd = process.cwd(), dryRun = false, run = spawnSync } = {}) {
    this.cwd = resolve(cwd);
    this.dryRun = dryRun;
    this.run = run;
    this.commands = [];
    this.output = [];
    this.cwd = this._read(['rev-parse', '--show-toplevel']);
  }

  _invoke(command, args, allowFailure = false) {
    const result = this.run(command, args, {
      cwd: this.cwd,
      encoding: 'utf8',
      env: { ...process.env, GIT_OPTIONAL_LOCKS: '0', GIT_TERMINAL_PROMPT: '0', GH_PROMPT_DISABLED: '1' },
      maxBuffer: 10 * 1024 * 1024,
      timeout: 60000,
    });
    if (result.error || result.status !== 0) {
      if (allowFailure) return null;
      throw new Error(`${command} 실행 실패: ${result.error?.message || result.stderr?.trim() || result.stdout?.trim() || result.status}`);
    }
    return result.stdout || '';
  }

  _read(args, { allowFailure = false, raw = false } = {}) {
    const output = this._invoke('git', args, allowFailure);
    return raw || output === null ? output : output.trim();
  }

  _change(args, command = 'git') {
    this.commands.push({ command, args: [...args] });
    if (!this.dryRun) {
      const output = this._invoke(command, args).trim();
      if (output) this.output.push(output);
    }
  }

  _begin() {
    this.commands = [];
    this.output = [];
  }

  _result(details = {}) {
    return { dryRun: this.dryRun, commands: [...this.commands], output: this.output.join('\n'), ...details };
  }

  inspect() {
    const branch = this._read(['symbolic-ref', '--quiet', '--short', 'HEAD'], { allowFailure: true });
    const head = this._read(['rev-parse', '--verify', 'HEAD'], { allowFailure: true });
    const upstream = branch ? this._read(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'], { allowFailure: true }) : null;
    const raw = this._read(['status', '--porcelain=v1', '-z', '--untracked-files=all', '--no-renames'], { raw: true });
    const changes = raw.split('\0').filter(Boolean).map((entry) => ({ status: entry.slice(0, 2), path: entry.slice(3) }));
    const counts = upstream && head ? this._read(['rev-list', '--left-right', '--count', `HEAD...${upstream}`]).split(/\s+/).map(Number) : [0, 0];
    return {
      root: this.cwd, branch, head, upstream, dirty: changes.length > 0, changes,
      status: changes.map((entry) => `${entry.status} ${entry.path}`).join('\n'),
      ahead: counts[0], behind: counts[1],
    };
  }

  status() {
    return this.inspect();
  }

  _ready({ clean = false, main = false } = {}) {
    const state = this.inspect();
    if (!state.branch || !state.head) throw new Error('커밋이 있는 브랜치에서 실행하세요. detached HEAD에서는 작업할 수 없습니다.');
    for (const name of ['MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply', 'sequencer', 'BISECT_LOG']) {
      if (existsSync(resolve(this.cwd, this._read(['rev-parse', '--git-path', name])))) {
        throw new Error(`진행 중인 Git 작업(${name})을 먼저 완료하세요.`);
      }
    }
    if (main && state.branch !== 'main') throw new Error('main 브랜치에서 실행하세요.');
    if (clean && state.dirty) throw new Error('작업 트리가 깨끗하지 않습니다. 변경 파일을 먼저 명시적으로 커밋하거나 직접 정리하세요.');
    return state;
  }

  _origin() {
    const remote = this._read(['remote', 'get-url', 'origin'], { allowFailure: true });
    if (!remote) throw new Error('origin 원격 저장소를 먼저 설정하세요.');
    return remote;
  }

  _fetch(branch) {
    this._origin();
    this._change(['fetch', '--no-tags', 'origin', `refs/heads/${branch}:refs/remotes/origin/${branch}`]);
  }

  _remoteRef(branch) {
    const ref = `refs/remotes/origin/${branch}`;
    if (!this._read(['rev-parse', '--verify', ref], { allowFailure: true })) {
      throw new Error(`origin/${branch} 정보가 없습니다. git fetch origin 후 다시 실행하세요.`);
    }
    return ref;
  }

  _name(name, prefix) {
    if (typeof name !== 'string' || !name || name.startsWith('-') || /[\x00-\x20\x7f]/.test(name) ||
      this._read(['check-ref-format', `${prefix}/${name}`], { allowFailure: true }) === null) {
      throw new Error('올바른 Git 이름을 입력하세요. 공백, 제어 문자, 잘못된 ref는 사용할 수 없습니다.');
    }
    return name;
  }

  _message(message) {
    if (typeof message !== 'string' || !message.trim() || message.includes('\0')) throw new Error('비어 있지 않은 설명을 입력하세요.');
    return message;
  }

  start(type, slug) {
    this._begin();
    this._ready({ clean: true, main: true });
    if (!BRANCH_TYPES.includes(type)) throw new Error(`작업 종류: ${BRANCH_TYPES.join(', ')}`);
    if (typeof slug !== 'string' || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new Error('작업 이름은 소문자, 숫자, 하이픈을 사용하세요. 예: video-upload');
    const branch = this._name(`${type}/${slug}`, 'refs/heads');
    if (this._read(['show-ref', '--verify', '--quiet', `refs/heads/${branch}`], { allowFailure: true }) !== null) throw new Error(`브랜치가 이미 있습니다: ${branch}`);
    this._fetch('main');
    const base = this._remoteRef('main');
    if (this._read(['merge-base', '--is-ancestor', 'HEAD', base], { allowFailure: true }) === null) {
      throw new Error('main에 원격에 없는 커밋이 있습니다. 먼저 검토하고 push하거나 분기 상태를 해결하세요.');
    }
    this._change(['merge', '--ff-only', base]);
    this._change(['switch', '--no-track', '-c', branch]);
    return this._result({ branch });
  }

  sync() {
    this._begin();
    const state = this._ready({ clean: true });
    if (state.upstream !== `origin/${state.branch}`) throw new Error(`origin/${state.branch} 추적 설정이 필요합니다. 새 작업 브랜치는 먼저 push하세요.`);
    this._fetch(state.branch);
    const ref = this._remoteRef(state.branch);
    const counts = this._read(['rev-list', '--left-right', '--count', `HEAD...${ref}`]).split(/\s+/).map(Number);
    if (counts[0] > 0 && counts[1] > 0) throw new Error('로컬과 원격 이력이 갈라졌습니다. 자동 rebase나 reset 없이 중단합니다. 직접 검토 후 merge하세요.');
    this._change(['merge', '--ff-only', ref]);
    return this._result({ branch: state.branch });
  }

  backToMain() {
    this._begin();
    this._ready({ clean: true });
    this._fetch('main');
    const ref = this._remoteRef('main');
    const main = 'refs/heads/main';
    if (!this._read(['rev-parse', '--verify', main], { allowFailure: true })) throw new Error('로컬 main 브랜치가 없습니다. 저장소의 기본 브랜치를 확인하세요.');
    const counts = this._read(['rev-list', '--left-right', '--count', `${main}...${ref}`]).split(/\s+/).map(Number);
    if (counts[0] > 0 && counts[1] > 0) throw new Error('main과 origin/main 이력이 갈라졌습니다. 현재 브랜치를 유지합니다. 직접 검토하세요.');
    if (counts[0] > 0) this._checkMainPush(main);
    this._change(['switch', 'main']);
    this._change(['merge', '--ff-only', ref]);
    return this._result({ branch: 'main' });
  }

  _paths(paths, state) {
    if (!Array.isArray(paths) || paths.length === 0) throw new Error('커밋할 파일을 하나 이상 명시적으로 선택하세요.');
    const selected = [...new Set(paths)];
    for (const path of selected) {
      if (typeof path !== 'string' || !path || isAbsolute(path) || path.startsWith(':') ||
        /[\\\x00-\x1f\x7f]/.test(path) || path.split('/').some((part) => ['', '.', '..', '.git'].includes(part))) {
        throw new Error('저장소 루트 기준의 정확한 개별 파일 경로를 사용하세요. 경로 이동과 Git pathspec은 허용하지 않습니다.');
      }
      let location = this.cwd;
      for (const part of path.split('/')) {
        location = join(location, part);
        let info;
        try { info = lstatSync(location); } catch (error) {
          if (error.code === 'ENOENT') continue;
          throw error;
        }
        if (info.isSymbolicLink()) throw new Error(`심볼릭 링크 경로는 선택할 수 없습니다: ${path}`);
        if (location === join(this.cwd, path) && !info.isFile()) throw new Error(`디렉터리 대신 개별 파일을 선택하세요: ${path}`);
      }
      if (!state.changes.some((change) => change.path === path)) throw new Error(`변경된 파일이 아닙니다: ${path}`);
    }
    return selected;
  }

  commit(message, paths) {
    this._begin();
    const state = this._ready();
    this._message(message);
    const selected = this._paths(paths, state);
    if (state.branch === 'main' && selected.some((path) => !isDocumentationOrConfig(path))) {
      throw new Error('main에서는 문서와 명시된 설정 파일만 커밋할 수 있습니다. 앱 소스는 작업 브랜치에서 커밋하세요.');
    }
    // --only records the selected working-tree files while retaining unrelated staged changes.
    // New files must first be known to the index; staged deletions must not be passed to git add.
    const untracked = selected.filter((path) => state.changes.some((change) => change.path === path && change.status === '??'));
    if (untracked.length) this._change(['--literal-pathspecs', 'add', '--', ...untracked]);
    this._change(['--literal-pathspecs', 'commit', '--only', '-m', message, '--', ...selected]);
    return this._result({ paths: selected });
  }

  _checkMainPush(head = 'HEAD') {
    const base = this._remoteRef('main');
    if (this._read(['merge-base', '--is-ancestor', base, head], { allowFailure: true }) === null) throw new Error('main을 origin/main과 먼저 동기화하세요.');
    const commits = this._read(['rev-list', `${base}..${head}`]).split('\n').filter(Boolean);
    for (const commit of commits) {
      // Check every incoming commit, including merged parents, so add-then-delete cannot bypass the policy.
      const files = this._read(['diff-tree', '--root', '-m', '--no-commit-id', '--name-only', '--no-renames', '-r', '-z', commit], { raw: true }).split('\0').filter(Boolean);
      if (files.some((path) => !isDocumentationOrConfig(path))) throw new Error('main에 앱 소스 변경 커밋이 있습니다. 작업 브랜치와 PR로 검토하세요.');
    }
  }

  push() {
    this._begin();
    const state = this._ready();
    this._origin();
    if (state.branch === 'main') {
      this._fetch('main');
      this._checkMainPush();
    }
    this._change(['-c', 'remote.origin.mirror=false', 'push', '--no-force', '--no-follow-tags', '--set-upstream', 'origin', `refs/heads/${state.branch}:refs/heads/${state.branch}`]);
    return this._result({ branch: state.branch });
  }

  tag(name, message) {
    this._begin();
    this._ready({ clean: true, main: true });
    this._name(name, 'refs/tags');
    this._message(message);
    if (this._read(['show-ref', '--verify', '--quiet', `refs/tags/${name}`], { allowFailure: true }) !== null) throw new Error(`태그가 이미 있습니다: ${name}`);
    this._fetch('main');
    if (this._read(['rev-parse', 'HEAD']) !== this._read(['rev-parse', this._remoteRef('main')])) throw new Error('main과 origin/main이 같은 커밋이어야 태그를 만들 수 있습니다. sync 또는 push하세요.');
    this._change(['tag', '--annotate', name, '--message', message]);
    return this._result({ tag: name });
  }

  publishTag(name) {
    this._begin();
    this._ready({ clean: true, main: true });
    this._name(name, 'refs/tags');
    const ref = `refs/tags/${name}`;
    if (this._read(['cat-file', '-t', ref], { allowFailure: true }) !== 'tag') throw new Error('먼저 설명이 있는 annotated tag를 생성하세요.');
    this._fetch('main');
    if (this._read(['merge-base', '--is-ancestor', `${ref}^{commit}`, this._remoteRef('main')], { allowFailure: true }) === null) throw new Error('origin/main에 포함된 커밋의 태그만 게시할 수 있습니다.');
    this._change(['-c', 'remote.origin.mirror=false', 'push', '--no-force', '--no-follow-tags', 'origin', `${ref}:${ref}`]);
    return this._result({ tag: name });
  }

  _githubRepository() {
    const remote = this._origin();
    let hostname;
    let pathname;
    if (/^[\w.-]+@[\w.-]+:/.test(remote)) {
      const match = remote.match(/^[\w.-]+@([\w.-]+):(.+)$/);
      [, hostname, pathname] = match;
    } else {
      let url;
      try { url = new URL(remote); } catch { throw new Error('PR을 만들려면 origin에 GitHub 저장소 URL이 필요합니다.'); }
      if (!['https:', 'ssh:'].includes(url.protocol)) throw new Error('PR origin은 HTTPS 또는 SSH GitHub URL이어야 합니다.');
      hostname = url.hostname;
      pathname = url.pathname.replace(/^\//, '');
    }
    pathname = pathname.replace(/\.git$/, '');
    if (!/^[\w.-]+\/[\w.-]+$/.test(pathname)) throw new Error('origin의 GitHub 소유자/저장소 경로를 확인하세요.');
    return `${hostname}/${pathname}`;
  }

  pr(title, body) {
    this._begin();
    const state = this._ready({ clean: true });
    if (state.branch === 'main') throw new Error('작업 브랜치에서 PR을 생성하세요.');
    this._message(title);
    this._message(body);
    const repository = this._githubRepository();
    if (state.upstream !== `origin/${state.branch}`) throw new Error('현재 작업 브랜치를 먼저 origin에 push하세요.');
    const remoteHead = this._read(['ls-remote', '--heads', 'origin', `refs/heads/${state.branch}`]).split(/\s+/)[0];
    if (remoteHead !== state.head) throw new Error('로컬과 원격 작업 브랜치가 다릅니다. 먼저 sync 또는 push하세요.');
    const existing = JSON.parse(this._invoke('gh', ['pr', 'list', '--repo', repository, '--head', state.branch, '--base', 'main', '--state', 'open', '--json', 'url,isCrossRepository']))
      .find((pullRequest) => pullRequest.isCrossRepository === false);
    if (existing) return this._result({ url: existing.url, existing: true });
    const args = ['pr', 'create', '--repo', repository, '--base', 'main', '--head', state.branch, '--draft', '--title', title, '--body-file'];
    if (this.dryRun) {
      this._change([...args, '<temporary-pr-body.md>'], 'gh');
    } else {
      const directory = mkdtempSync(join(tmpdir(), 'git-workflow-pr-'));
      try {
        const file = join(directory, 'body.md');
        writeFileSync(file, body, { mode: 0o600 });
        this._change([...args, file], 'gh');
      } finally {
        rmSync(directory, { recursive: true, force: true });
      }
    }
    return this._result({ url: this.output.at(-1) || null, existing: false });
  }
}
