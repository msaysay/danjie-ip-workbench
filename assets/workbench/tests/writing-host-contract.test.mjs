import test from 'node:test';
import assert from 'node:assert/strict';
import {DESKTOP_COMMANDS} from '../src/storycueContract.js';
import {MANUAL_FALLBACK,WRITING_HOSTS,WRITING_STEPS,installMessage,stepCanAdvance,syncFeedback,writingReady} from '../src/writingHostContract.js';

test('writing wizard is four steps and either host is enough', () => {
  assert.equal(WRITING_STEPS.map(item => item.id).join(','), 'host,install,verify,done');
  assert.equal(WRITING_HOSTS.workbuddy.package, '@tencent-ai/codebuddy-code');
  assert.equal(WRITING_HOSTS.workbuddy.command, 'codebuddy');
  assert.equal(WRITING_HOSTS.codex.package, '@openai/codex');
  assert.equal(WRITING_HOSTS.codex.command, 'codex');
  assert.match(WRITING_HOSTS.workbuddy.installUrl, /^https:\/\/www\.codebuddy\.cn\/docs\/cli\/installation/);
  assert.match(WRITING_HOSTS.codex.installUrl, /^https:\/\/developers\.openai\.com\/codex\/cli/);
  assert.equal(stepCanAdvance('host', {host: ''}), false);
  assert.equal(stepCanAdvance('host', {host: 'codex'}), true);
  assert.equal(stepCanAdvance('install', {host: 'codex'}), true);
  assert.equal(stepCanAdvance('verify', {host: ''}), true);
  assert.equal(stepCanAdvance('done', {host: 'workbuddy'}), false);
});

test('install copy names a found command and still allows a missing CLI', () => {
  assert.match(installMessage({found: true, via: ['path'], command: 'codex', path: '/usr/local/bin/codex', package: '@openai/codex'}), /已找到命令 codex：\/usr\/local\/bin\/codex/);
  assert.match(installMessage({found: true, via: ['npm'], packageFound: true, command: 'codebuddy', package: '@tencent-ai/codebuddy-code', path: ''}), /已找到安装包 @tencent-ai\/codebuddy-code/);
  assert.match(installMessage({found: false, via: [], command: 'codebuddy', package: '@tencent-ai/codebuddy-code'}), /还没找到命令 codebuddy/);
  assert.match(MANUAL_FALLBACK, /今日选题\.json/);
  assert.match(MANUAL_FALLBACK, /再点同步/);
});

test('completion is green after sync or a file from today, and feedback stays specific', () => {
  assert.equal(writingReady(null), false);
  assert.equal(writingReady({syncedToday: true, topicFile: {exists: false}}), true);
  assert.equal(writingReady({syncedToday: false, topicFile: {exists: true, matchesToday: true, writtenToday: false}}), true);
  assert.equal(writingReady({syncedToday: false, topicFile: {exists: true, matchesToday: false, writtenToday: true}}), true);
  assert.equal(writingReady({syncedToday: false, topicFile: {exists: true, matchesToday: false, writtenToday: false}}), false);
  assert.equal(syncFeedback({errors: ['今日选题还没接入'], status: {syncedToday: false}}), '今日选题还没接入');
  assert.match(syncFeedback({errors: [], status: {syncedToday: true}}), /同步成功/);
  assert.match(syncFeedback({status: {syncedToday: false, topicFile: {exists: false}}}), /放进业务文件夹/);
  assert.equal(DESKTOP_COMMANDS.doctor, 'npm run desktop:doctor');
  assert.match(DESKTOP_COMMANDS.connectCodex, /--host codex/);
  assert.match(DESKTOP_COMMANDS.connectWorkbuddy, /--host workbuddy/);
});
