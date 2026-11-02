/** Student-facing rules for the topic list and the generate-script result. */

export const HANDOFF_MARK = '还没接到新的写稿结果';

export function olderTopicsOpen(todayCount, olderCount) {
  return todayCount === 0 && olderCount > 0;
}

export function draftResultMessage(error) {
  const text = String(error || '');
  if (!text) {
    return {kind: 'success', text: '脚本已整理进这一题，接着改成你愿意讲的话。这一步没有打开 WorkBuddy。'};
  }
  if (text.includes(HANDOFF_MARK)) {
    return {
      kind: 'handoff',
      text: '这题还没有现成整稿，已写好「待写脚本.md」。请到 WorkBuddy 或 Codex 里接着写，写完再点同步。工作台不会弹出浏览器，也不会把四段提纲拼成稿。写稿和抖音、视频号扫码不是同一件事。',
    };
  }
  return {kind: 'error', text};
}
