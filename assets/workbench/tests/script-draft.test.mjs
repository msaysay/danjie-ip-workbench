import test from 'node:test';
import assert from 'node:assert/strict';
import {HANDOFF_MARK, draftResultMessage, olderTopicsOpen} from '../src/scriptDraft.js';

test('older topics stay open only when today has none', () => {
  assert.equal(olderTopicsOpen(0, 12), true);
  assert.equal(olderTopicsOpen(1, 12), false);
  assert.equal(olderTopicsOpen(0, 0), false);
});

test('a prepared draft and a WorkBuddy handoff read differently', () => {
  const success = draftResultMessage('');
  assert.equal(success.kind, 'success');
  assert.match(success.text, /脚本已整理/);
  assert.match(success.text, /没有打开 WorkBuddy/);
  const handoff = draftResultMessage('前文。' + HANDOFF_MARK + '。后文');
  assert.equal(handoff.kind, 'handoff');
  assert.match(handoff.text, /待写脚本\.md/);
  assert.match(handoff.text, /不会弹出浏览器/);
  assert.match(handoff.text, /不是同一件事/);
  assert.equal(draftResultMessage('这条选题有新修改').kind, 'error');
});
