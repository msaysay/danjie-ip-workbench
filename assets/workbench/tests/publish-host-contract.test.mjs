import test from 'node:test';
import assert from 'node:assert/strict';
import {OPEN_HOST_NOTE, PASTE_FALLBACK, UNDERSTANDING_INTRO, copyHandoffMessage, prepareResultMessage, transcriptNote} from '../src/publishHostContract.js';

test('publish handoff copy keeps the writing host separate from platform QR login', () => {
  assert.match(OPEN_HOST_NOTE, /写稿窗口/);
  assert.match(OPEN_HOST_NOTE, /不是抖音或视频号的扫码/);
  assert.match(UNDERSTANDING_INTRO, /WorkBuddy 或 Codex/);
  assert.doesNotMatch(UNDERSTANDING_INTRO, /install_optional/);
  assert.match(PASTE_FALLBACK, /粘贴发布文字/);
  assert.match(PASTE_FALLBACK, /不会自动发布/);
  const copied = copyHandoffMessage('Codex');
  assert.match(copied, /Codex/);
  assert.match(copied, /不是抖音或视频号的扫码/);
  assert.match(prepareResultMessage({handoff: true, message: '请让 Codex 看这条成片。打开写稿窗口会弹出本机终端，这不是抖音或视频号的扫码。'}), /不是抖音或视频号的扫码/);
  assert.match(prepareResultMessage({}), /正在根据成片准备文字/);
  assert.match(transcriptNote('host_understanding'), /写稿 AI/);
  assert.match(transcriptNote('existing_exact_video'), /同一条视频已有的文字/);
  assert.match(transcriptNote('offline_asr'), /请核对原话/);
});
