import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('./git-workflow.mjs', import.meta.url));

test('CLI requires explicit execution and preserves unrelated staging', (t) => {
  const cwd = mkdtempSync(join(tmpdir(), 'tennis-git-cli-'));
  t.after(() => rmSync(cwd, { recursive: true, force: true }));
  const env = {
    ...process.env,
    GIT_CONFIG_GLOBAL: '/dev/null',
    GIT_CONFIG_NOSYSTEM: '1',
    GIT_AUTHOR_NAME: 'CLI Test',
    GIT_AUTHOR_EMAIL: 'cli-test@example.invalid',
    GIT_COMMITTER_NAME: 'CLI Test',
    GIT_COMMITTER_EMAIL: 'cli-test@example.invalid',
  };
  function git(...args) {
    const result = spawnSync('git', args, { cwd, env, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    return result.stdout.trim();
  }
  function cli(...args) {
    return spawnSync(process.execPath, [script, ...args], { cwd, env, input: '', encoding: 'utf8' });
  }

  assert.equal(cli('--help').status, 0, 'Help must work outside a Git repository');
  git('init', '--initial-branch=main');
  git('config', 'commit.gpgsign', 'false');
  git('config', 'core.hooksPath', '/dev/null');
  writeFileSync(join(cwd, 'README.md'), 'Initial\n');
  writeFileSync(join(cwd, 'other.txt'), 'Initial\n');
  git('add', 'README.md', 'other.txt');
  git('commit', '-m', 'Initial');
  git('switch', '-c', 'chore/cli-test');
  writeFileSync(join(cwd, 'README.md'), 'Updated\n');
  writeFileSync(join(cwd, 'other.txt'), 'Preserve staged\n');
  git('add', 'other.txt');
  const head = git('rev-parse', 'HEAD');
  const staged = git('diff', '--cached', '--binary');
  const command = ['commit', '--message', 'docs: update guide', '--file', 'README.md'];

  for (const args of [
    [...command],
    [...command, '--yes', '--dry-run'],
    [...command, '--yes', '--typo'],
    ['status', '--message', 'unused'],
    ['commit', 'extra-command', '--yes'],
    ['--yes'],
  ]) {
    const result = cli(...args);
    assert.notEqual(result.status, 0, `Unexpected execution: ${args.join(' ')}`);
    assert.equal(git('rev-parse', 'HEAD'), head);
    assert.equal(git('diff', '--cached', '--binary'), staged);
  }

  assert.equal(cli().status, 0, 'Non-interactive menu prints help');
  const preview = cli(...command, '--dry-run');
  assert.equal(preview.status, 0, preview.stderr);
  assert.match(preview.stdout, /commit --only/);
  assert.match(preview.stdout, /chore\/cli-test/);
  assert.equal(git('rev-parse', 'HEAD'), head);
  assert.equal(git('diff', '--cached', '--binary'), staged);

  const executed = cli(...command, '--yes');
  assert.equal(executed.status, 0, executed.stderr);
  assert.notEqual(git('rev-parse', 'HEAD'), head);
  assert.equal(git('show', 'HEAD:README.md'), 'Updated');
  assert.equal(git('show', 'HEAD:other.txt'), 'Initial');
  assert.equal(git('diff', '--cached', '--binary'), staged);
  assert.equal(readFileSync(join(cwd, 'other.txt'), 'utf8'), 'Preserve staged\n');
});
