/** Shared rules for the writing-host wizard. No model keys live here. */

export const WRITING_STEPS = [
  {id: 'host', title: '选一个写稿的 AI'},
  {id: 'install', title: '安装或打开'},
  {id: 'verify', title: '跑一次并同步'},
  {id: 'done', title: '完成'},
];

export const WRITING_HOSTS = {
  workbuddy: {
    label: 'WorkBuddy',
    command: 'codebuddy',
    package: '@tencent-ai/codebuddy-code',
    installUrl: 'https://www.codebuddy.cn/docs/cli/installation',
    appUrl: 'https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Automation-Guide',
    open: '打开写稿窗口会弹出本机终端里的 codebuddy。请选择「国内站」并回车，浏览器才会出现。这不是发布账号扫码。',
  },
  codex: {
    label: 'Codex',
    command: 'codex',
    package: '@openai/codex',
    installUrl: 'https://developers.openai.com/codex/cli',
    appUrl: 'https://developers.openai.com/codex/cli',
    open: '打开写稿窗口会运行 codex login，由它弹出浏览器。这不是发布账号扫码。',
  },
};

export const MANUAL_FALLBACK = '没有命令行也可以：把写好的「今日选题.json」放进业务文件夹，再点同步。';

export function writingReady(status) {
  if (!status) return false;
  if (status.syncedToday) return true;
  const file = status.topicFile || {};
  return !!(file.exists && (file.matchesToday || file.writtenToday));
}

export function stepCanAdvance(stepId, status) {
  if (stepId === 'done') return false;
  if (stepId === 'host') return status?.host === 'workbuddy' || status?.host === 'codex';
  return true;
}

export function installMessage(host) {
  if (!host) return '先选择 WorkBuddy 或 Codex。';
  if (host.found && host.via?.includes('path')) return `已找到命令 ${host.command}${host.path ? '：' + host.path : ''}。`;
  if (host.found && host.packageFound) return `已找到安装包 ${host.package}。当前窗口还调不到命令 ${host.command}。`;
  return `还没找到命令 ${host.command}，也没找到安装包 ${host.package}。可以先安装，也可以先用已经打开的窗口。`;
}

export function syncFeedback({errors, status} = {}) {
  const list = Array.isArray(errors) ? errors.filter(Boolean) : [];
  if (list.length) return list.join('；');
  if (status?.syncedToday) return '同步成功，今天的题已经在选题页。';
  const file = status?.topicFile || {};
  if (file.exists && (file.matchesToday || file.writtenToday)) return '文件夹里已经有今天的选题文件。';
  if (file.exists) return '文件夹里有选题文件，但不是今天的。请让 AI 把 date 写成今天后再同步。';
  return '还没读到今天的选题文件。可以让 AI 写好，或自己把「今日选题.json」放进业务文件夹，然后再同步。';
}
