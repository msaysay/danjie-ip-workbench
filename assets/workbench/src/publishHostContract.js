/** Copy for handing a finished video to the writing host. No model keys live here. */

export const OPEN_HOST_NOTE = '打开写稿窗口会弹出本机终端。这不是抖音或视频号的扫码。';

export const PASTE_FALLBACK = '它填不回去时，用旁边的「粘贴发布文字」。不会自动发布。';

export const UNDERSTANDING_INTRO = '这一步先用同一条视频已有的文字。本机已经装了离线听写、并且接通了自动写作时，会直接拟标题和说明。否则交给你正在用的 WorkBuddy 或 Codex 看这条成片。你仍然可以自己改，不拟也能发。';

export function transcriptNote(kind) {
  if (kind === 'existing_exact_video') return '这次用了同一条视频已有的文字，没有重新听一遍。';
  if (kind === 'host_understanding') return '这版原话是写稿 AI 整理的，请对照成片核对。';
  if (kind === 'offline_asr') return '从成片里听出来的，请核对原话。';
  return '先核对原话，再决定对外怎么说。';
}

export function copyHandoffMessage(hostLabel) {
  const name = hostLabel || 'WorkBuddy 或 Codex';
  return `整理发布文字的话已复制。粘到${name}。${OPEN_HOST_NOTE}${PASTE_FALLBACK}`;
}

export function prepareResultMessage(result) {
  if (result?.handoff) return result.message || `请让写稿 AI 看这条成片。${OPEN_HOST_NOTE}`;
  return '正在根据成片准备文字。封面在下面单独做，不做也能发。';
}
