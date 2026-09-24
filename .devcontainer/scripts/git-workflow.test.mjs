import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import test from 'node:test';

import { GitWorkflow } from './git-workflow-core.mjs';

const gitEnvironment = {
  ...process.env,
  GIT_CONFIG_GLOBAL: '/dev/null',
  GIT_CONFIG_NOSYSTEM: '1',
  GIT_TERMINAL_PROMPT: '0',
  GIT_OPTIONAL_LOCKS: '0',
  GIT_AUTHOR_NAME: 'Workflow Test',
  GIT_AUTHOR_EMAIL: 'workflow-test@example.invalid',
  GIT_COMMITTER_NAME: 'Workflow Test',
  GIT_COMMITTER_EMAIL: 'workflow-test@example.invalid',
};

function run(command, args, options = {}) {
  return spawnSync(command, args, { ...options, encoding: 'utf8', env: gitEnvironment });
}

function git(cwd, ...args) {
  const result = run('git', args, { cwd });
  assert.equal(result.status, 0, `git ${args.join(' ')} failed: ${result.stderr}`);
  return result.stdout.trim();
}

function write(root, path, content) {
  const target = join(root, path);
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, content);
}

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'tennis-git-workflow-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const origin = join(root, 'origin.git');
  const repo = join(root, 'repo');
  git(root, 'init', '--bare', '--initial-branch=main', origin);
  git(root, 'clone', origin, repo);
  git(repo, 'config', 'commit.gpgsign', 'false');
  git(repo, 'config', 'tag.gpgsign', 'false');
  git(repo, 'config', 'core.hooksPath', '/dev/null');
  write(repo, 'README.md', 'Initial documentation\n');
  write(repo, 'lib/main.dart', 'void main() {}\n');
  write(repo, 'docs/old guide.md', 'Old guide\n');
  git(repo, 'add', '--all');
  git(repo, 'commit', '-m', 'chore: initial fixture');
  git(repo, 'push', '-u', 'origin', 'main');
  return { root, origin, repo, initial: git(repo, 'rev-parse', 'HEAD') };
}

function workflow(f, options = {}) {
  return new GitWorkflow({ cwd: f.repo, run, ...options });
}

function commitFile(repo, path, content, message = 'test: update fixture') {
  write(repo, path, content);
  git(repo, 'add', '--', path);
  git(repo, 'commit', '-m', message);
  return git(repo, 'rev-parse', 'HEAD');
}

function peer(f) {
  const repo = join(f.root, 'peer');
  git(f.root, 'clone', f.origin, repo);
  return repo;
}

function snapshot(f) {
  return {
    head: git(f.repo, 'rev-parse', 'HEAD'),
    branch: git(f.repo, 'branch', '--show-current'),
    refs: git(f.repo, 'show-ref'),
    status: git(f.repo, 'status', '--porcelain=v1', '-z'),
    staged: git(f.repo, 'diff', '--cached', '--binary'),
    config: readFileSync(join(f.repo, '.git/config'), 'utf8'),
    remoteRefs: git(f.origin, 'show-ref'),
  };
}

test('inspect reports branch tracking and filenames with spaces', (t) => {
  const f = fixture(t);
  const clean = workflow(f).inspect();
  assert.equal(clean.root, f.repo);
  assert.equal(clean.branch, 'main');
  assert.equal(clean.upstream, 'origin/main');
  assert.equal(clean.dirty, false);
  assert.equal(clean.ahead, 0);
  assert.equal(clean.behind, 0);

  write(f.repo, 'docs/new guide.md', 'New guide\n');
  const dirty = workflow(f).inspect();
  assert.equal(dirty.dirty, true);
  assert.ok(dirty.changes.some((change) => change.path === 'docs/new guide.md'));
});

test('start fetches current main and creates a branch without inheriting its upstream', (t) => {
  const f = fixture(t);
  const other = peer(f);
  const newest = commitFile(other, 'README.md', 'Updated remotely\n');
  git(other, 'push', 'origin', 'main');

  workflow(f).start('feature', 'serve-analysis');

  assert.equal(git(f.repo, 'branch', '--show-current'), 'feature/serve-analysis');
  assert.equal(git(f.repo, 'rev-parse', 'HEAD'), newest);
  assert.equal(git(f.repo, 'for-each-ref', '--format=%(upstream)', 'refs/heads/feature/serve-analysis'), '');
});

test('start refuses dirty, detached, and conflicted repositories without changing HEAD', async (t) => {
  for (const state of ['dirty', 'detached', 'merge']) {
    await t.test(state, (t) => {
      const f = fixture(t);
      if (state === 'dirty') write(f.repo, 'README.md', 'Uncommitted work\n');
      if (state === 'detached') git(f.repo, 'checkout', '--detach');
      if (state === 'merge') {
        git(f.repo, 'switch', '-c', 'conflict');
        commitFile(f.repo, 'README.md', 'Other branch\n');
        git(f.repo, 'switch', 'main');
        commitFile(f.repo, 'README.md', 'Main branch\n');
        assert.equal(run('git', ['merge', 'conflict'], { cwd: f.repo }).status, 1);
      }
      const before = snapshot(f);
      assert.throws(() => workflow(f).start('feature', 'new-work'));
      assert.deepEqual(snapshot(f), before);
    });
  }
});

test('start refuses main with local commits rather than carrying them to a new branch', (t) => {
  const f = fixture(t);
  commitFile(f.repo, 'README.md', 'Unpublished documentation\n');
  const before = snapshot(f);
  assert.throws(() => workflow(f).start('feature', 'new-work'));
  assert.equal(git(f.repo, 'rev-parse', 'HEAD'), before.head);
  assert.equal(git(f.repo, 'branch', '--show-current'), 'main');
  assert.equal(git(f.repo, 'branch', '--format=%(refname:short)'), 'main');
  assert.equal(git(f.origin, 'rev-parse', 'main'), f.initial);
});

test('commit includes only selected new, modified, and deleted files and preserves unrelated staging', (t) => {
  const f = fixture(t);
  workflow(f).start('feature', 'selected-files');
  write(f.repo, 'README.md', 'Keep this staged\n');
  git(f.repo, 'add', 'README.md');
  write(f.repo, 'lib/main.dart', 'void main() { print("tennis"); }\n');
  write(f.repo, 'docs/new guide.md', 'New guide\n');
  rmSync(join(f.repo, 'docs/old guide.md'));

  workflow(f).commit('feat: update selected files', ['lib/main.dart', 'docs/new guide.md', 'docs/old guide.md']);

  assert.equal(git(f.repo, 'show', 'HEAD:README.md'), 'Initial documentation');
  assert.equal(git(f.repo, 'show', 'HEAD:docs/new guide.md'), 'New guide');
  assert.equal(git(f.repo, 'show', 'HEAD:lib/main.dart'), 'void main() { print("tennis"); }');
  assert.equal(run('git', ['cat-file', '-e', 'HEAD:docs/old guide.md'], { cwd: f.repo }).status, 128);
  assert.equal(git(f.repo, 'diff', '--cached', '--name-only'), 'README.md');
});

test('main accepts documentation commits and refuses application source without staging it', (t) => {
  const f = fixture(t);
  write(f.repo, 'lib/main.dart', 'void main() { print("uncommitted"); }\n');
  const before = snapshot(f);
  assert.throws(() => workflow(f).commit('feat: application change', ['lib/main.dart']));
  assert.deepEqual(snapshot(f), before);

  write(f.repo, 'README.md', 'Development instructions\n');
  workflow(f).commit('docs: update instructions', ['README.md']);
  assert.equal(git(f.repo, 'show', 'HEAD:README.md'), 'Development instructions');
  assert.equal(git(f.repo, 'show', 'HEAD:lib/main.dart'), 'void main() {}');
});

test('commit treats wildcard characters in a filename literally', (t) => {
  const f = fixture(t);
  workflow(f).start('feature', 'literal-paths');
  const selected = 'docs/[guide].md';
  write(f.repo, selected, 'Selected file\n');
  write(f.repo, 'docs/g.md', 'Unselected file\n');

  workflow(f).commit('test: literal filename', [selected]);

  assert.equal(git(f.repo, 'show', `HEAD:${selected}`), 'Selected file');
  assert.equal(run('git', ['cat-file', '-e', 'HEAD:docs/g.md'], { cwd: f.repo }).status, 128);
  assert.ok(git(f.repo, 'status', '--porcelain').includes('docs/g.md'));
});

test('commit rejects path traversal, escaping symlinks, Git metadata, and pathspec expressions', (t) => {
  const f = fixture(t);
  workflow(f).start('feature', 'safe-paths');
  write(f.root, 'outside/secret.txt', 'Outside repository\n');
  write(f.repo, ':(glob)*', 'Do not interpret this as a pathspec\n');
  symlinkSync(join(f.root, 'outside'), join(f.repo, 'linked'), 'dir');
  const before = snapshot(f);

  for (const path of ['../outside/secret.txt', join(f.root, 'outside/secret.txt'), 'linked/secret.txt', '.git/config', ':(glob)*']) {
    assert.throws(() => workflow(f).commit('test: invalid selection', [path]), path);
    assert.deepEqual(snapshot(f), before);
  }
  assert.equal(readFileSync(join(f.root, 'outside/secret.txt'), 'utf8'), 'Outside repository\n');
});

test('sync fast-forwards a clean main to the remote commit', (t) => {
  const f = fixture(t);
  const other = peer(f);
  const newest = commitFile(other, 'README.md', 'Synced documentation\n');
  git(other, 'push', 'origin', 'main');

  workflow(f).sync();

  assert.equal(git(f.repo, 'rev-parse', 'HEAD'), newest);
  assert.equal(readFileSync(join(f.repo, 'README.md'), 'utf8'), 'Synced documentation\n');
});

test('sync refuses diverged history and preserves the local commit', (t) => {
  const f = fixture(t);
  workflow(f).start('feature', 'diverged');
  git(f.repo, 'push', '-u', 'origin', 'feature/diverged');
  const other = peer(f);
  git(other, 'switch', '--track', 'origin/feature/diverged');
  commitFile(other, 'README.md', 'Remote work\n');
  git(other, 'push');
  const local = commitFile(f.repo, 'lib/main.dart', 'void main() { print("local"); }\n');

  assert.throws(() => workflow(f).sync());

  assert.equal(git(f.repo, 'rev-parse', 'HEAD'), local);
  assert.equal(git(f.repo, 'log', '-1', '--format=%P').split(' ').length, 1);
  assert.equal(readFileSync(join(f.repo, 'lib/main.dart'), 'utf8'), 'void main() { print("local"); }\n');
});

test('backToMain updates main while preserving the work branch and its commits', (t) => {
  const f = fixture(t);
  workflow(f).start('feature', 'return-home');
  const work = commitFile(f.repo, 'lib/main.dart', 'void main() { print("feature"); }\n');
  const other = peer(f);
  const newest = commitFile(other, 'README.md', 'Main advanced\n');
  git(other, 'push', 'origin', 'main');

  workflow(f).backToMain();

  assert.equal(git(f.repo, 'branch', '--show-current'), 'main');
  assert.equal(git(f.repo, 'rev-parse', 'HEAD'), newest);
  assert.equal(git(f.repo, 'rev-parse', 'feature/return-home'), work);
});

test('backToMain refuses dirty work and unsafe local main without switching branches', async (t) => {
  for (const state of ['dirty', 'diverged', 'source-ahead']) {
    await t.test(state, (t) => {
      const f = fixture(t);
      workflow(f).start('feature', 'stay-here');
      if (state === 'dirty') write(f.repo, 'README.md', 'Uncommitted feature work\n');
      if (state !== 'dirty') {
        git(f.repo, 'switch', 'main');
        commitFile(f.repo, state === 'source-ahead' ? 'lib/main.dart' : 'README.md', 'Local main work\n');
        git(f.repo, 'switch', 'feature/stay-here');
      }
      if (state === 'diverged') {
        const other = peer(f);
        commitFile(other, 'README.md', 'Remote main work\n');
        git(other, 'push', 'origin', 'main');
      }
      const head = git(f.repo, 'rev-parse', 'HEAD');
      const main = git(f.repo, 'rev-parse', 'main');

      assert.throws(() => workflow(f).backToMain());

      assert.equal(git(f.repo, 'branch', '--show-current'), 'feature/stay-here');
      assert.equal(git(f.repo, 'rev-parse', 'HEAD'), head);
      assert.equal(git(f.repo, 'rev-parse', 'main'), main);
    });
  }
});

test('push sets a work branch upstream and publishes the selected branch', (t) => {
  const f = fixture(t);
  workflow(f).start('feature', 'publish');
  const head = commitFile(f.repo, 'lib/main.dart', 'void main() { print("published"); }\n');

  workflow(f).push();

  assert.equal(git(f.repo, 'rev-parse', '--abbrev-ref', '@{upstream}'), 'origin/feature/publish');
  assert.equal(git(f.origin, 'rev-parse', 'refs/heads/feature/publish'), head);
  assert.equal(git(f.origin, 'rev-parse', 'refs/heads/main'), f.initial);
});

test('main push allows documentation-only commits', (t) => {
  const f = fixture(t);
  write(f.repo, 'README.md', 'Published instructions\n');
  workflow(f).commit('docs: update instructions', ['README.md']);

  workflow(f).push();

  assert.equal(git(f.origin, 'rev-parse', 'refs/heads/main'), git(f.repo, 'rev-parse', 'HEAD'));
});

test('main push detects source commits even when a subsequent revert erases the net diff', (t) => {
  const f = fixture(t);
  commitFile(f.repo, 'lib/main.dart', 'void main() { print("source change"); }\n');
  git(f.repo, 'revert', '--no-edit', 'HEAD');
  assert.equal(git(f.repo, 'diff', 'origin/main', 'HEAD'), '');
  const head = git(f.repo, 'rev-parse', 'HEAD');

  assert.throws(() => workflow(f).push());

  assert.equal(git(f.repo, 'rev-parse', 'HEAD'), head);
  assert.equal(git(f.origin, 'rev-parse', 'refs/heads/main'), f.initial);
});

test('tag creates an annotated immutable tag and publishes only the requested tag', (t) => {
  const f = fixture(t);
  workflow(f).tag('v0.1.0', 'Development environment ready');
  assert.equal(git(f.repo, 'cat-file', '-t', 'refs/tags/v0.1.0'), 'tag');
  assert.equal(git(f.repo, 'rev-parse', 'v0.1.0^{}'), f.initial);
  const object = git(f.repo, 'rev-parse', 'refs/tags/v0.1.0');
  assert.throws(() => workflow(f).tag('v0.1.0', 'Overwrite existing tag'));
  assert.equal(git(f.repo, 'rev-parse', 'refs/tags/v0.1.0'), object);

  git(f.repo, 'tag', '-a', 'unrelated-tag', '-m', 'Keep local');
  workflow(f).publishTag('v0.1.0');
  assert.equal(git(f.origin, 'rev-parse', 'refs/tags/v0.1.0'), object);
  assert.equal(git(f.origin, 'tag', '--list'), 'v0.1.0');
});

test('tag refuses dirty main, unpublished main, and work branches', async (t) => {
  for (const state of ['dirty', 'ahead', 'feature']) {
    await t.test(state, (t) => {
      const f = fixture(t);
      if (state === 'dirty') write(f.repo, 'README.md', 'Uncommitted\n');
      if (state === 'ahead') commitFile(f.repo, 'README.md', 'Unpublished\n');
      if (state === 'feature') workflow(f).start('feature', 'tag-attempt');

      assert.throws(() => workflow(f).tag('v0.1.0', 'Invalid release state'));

      assert.equal(git(f.repo, 'tag', '--list'), '');
      assert.equal(git(f.origin, 'tag', '--list'), '');
    });
  }
});

test('publishTag refuses lightweight tags', (t) => {
  const f = fixture(t);
  git(f.repo, 'tag', 'v0.1.0');

  assert.throws(() => workflow(f).publishTag('v0.1.0'));

  assert.equal(git(f.origin, 'tag', '--list'), '');
});

function githubFixture(t, { existing = [] } = {}) {
  const f = fixture(t);
  workflow(f).start('feature', 'review');
  commitFile(f.repo, 'lib/main.dart', 'void main() { print("review"); }\n');
  workflow(f).push();
  git(f.repo, 'remote', 'set-url', 'origin', 'https://github.com/example/tennis-ai.git');
  const calls = [];
  const bodies = [];
  const mockRun = (command, args, options) => {
    if (command === 'git') {
      // Keep all Git operations real and local, including the PR's remote-head check.
      const localArgs = args[0] === 'ls-remote' ? args.map((arg) => arg === 'origin' ? f.origin : arg) : args;
      return run(command, localArgs, options);
    }
    assert.equal(command, 'gh');
    calls.push([...args]);
    if (args[0] === 'pr' && args[1] === 'list') {
      return { status: 0, stdout: JSON.stringify(existing), stderr: '' };
    }
    assert.deepEqual(args.slice(0, 2), ['pr', 'create']);
    bodies.push(readFileSync(args[args.indexOf('--body-file') + 1], 'utf8'));
    return { status: 0, stdout: 'https://github.com/example/tennis-ai/pull/1\n', stderr: '' };
  };
  return { ...f, calls, bodies, mockRun };
}

test('pr creates a draft for the explicit work branch and preserves multiline body text', (t) => {
  const f = githubFixture(t);
  const title = 'feat: review $(literal-title)';
  const body = 'Application changes.\n\nValidation: `npm test`\nLiteral $HOME and \\n stay intact.\n';

  const result = workflow(f, { run: f.mockRun }).pr(title, body);

  assert.equal(result.url, 'https://github.com/example/tennis-ai/pull/1');
  assert.equal(result.existing, false);
  assert.deepEqual(f.bodies, [body]);
  const create = f.calls.find((args) => args[1] === 'create');
  assert.ok(create.includes('--draft'));
  assert.equal(create[create.indexOf('--title') + 1], title);
  assert.equal(create[create.indexOf('--base') + 1], 'main');
  assert.equal(create[create.indexOf('--head') + 1], 'feature/review');
  assert.equal(create[create.indexOf('--repo') + 1], 'github.com/example/tennis-ai');
});

test('pr returns an existing open PR without creating another', (t) => {
  const url = 'https://github.com/example/tennis-ai/pull/7';
  const f = githubFixture(t, { existing: [{ url, isCrossRepository: false }] });

  const result = workflow(f, { run: f.mockRun }).pr('Existing work', 'Already under review.');

  assert.equal(result.existing, true);
  assert.equal(result.url, url);
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0][1], 'list');
});

test('pr ignores a same-named branch from a fork', (t) => {
  const f = githubFixture(t, { existing: [{ url: 'https://github.com/example/tennis-ai/pull/9', isCrossRepository: true }] });

  const result = workflow(f, { run: f.mockRun }).pr('Our branch', 'Create the local repository PR.');

  assert.equal(result.existing, false);
  assert.equal(result.url, 'https://github.com/example/tennis-ai/pull/1');
  assert.equal(f.calls.filter((args) => args[1] === 'create').length, 1);
});

test('pr refuses unpublished commits before invoking GitHub', (t) => {
  const f = githubFixture(t);
  commitFile(f.repo, 'README.md', 'Unpublished follow-up\n');

  assert.throws(() => workflow(f, { run: f.mockRun }).pr('Unpublished work', 'Review request.'));

  assert.equal(f.calls.length, 0);
});

test('pr dry-run does not create or alter a PR', (t) => {
  const f = githubFixture(t);
  const before = snapshot(f);

  const result = workflow(f, { run: f.mockRun, dryRun: true }).pr('Preview review', 'Preview body.');

  assert.equal(result.dryRun, true);
  assert.ok(result.commands.some(({ command, args }) => command === 'gh' && args[1] === 'create'));
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0][1], 'list');
  assert.deepEqual(snapshot(f), before);
});

test('dry-run branch, commit, push, and tag actions leave local and remote state unchanged', async (t) => {
  const actions = {
    start: (f) => workflow(f, { dryRun: true }).start('feature', 'preview'),
    backToMain: (f) => workflow(f, { dryRun: true }).backToMain(),
    commit: (f) => workflow(f, { dryRun: true }).commit('docs: preview', ['README.md']),
    push: (f) => workflow(f, { dryRun: true }).push(),
    tag: (f) => workflow(f, { dryRun: true }).tag('v0.1.0', 'Preview tag'),
    publishTag: (f) => workflow(f, { dryRun: true }).publishTag('v0.1.0'),
  };
  for (const [action, execute] of Object.entries(actions)) {
    await t.test(action, (t) => {
      const f = fixture(t);
      if (action === 'backToMain') workflow(f).start('feature', 'preview-return');
      if (action === 'commit') write(f.repo, 'README.md', 'Preview only\n');
      if (action === 'push') commitFile(f.repo, 'README.md', 'Unpublished\n');
      if (action === 'publishTag') git(f.repo, 'tag', '-a', 'v0.1.0', '-m', 'Local tag');
      const before = snapshot(f);

      const result = execute(f);

      assert.equal(result.dryRun, true);
      assert.ok(result.commands.length > 0);
      assert.deepEqual(snapshot(f), before);
    });
  }
});
