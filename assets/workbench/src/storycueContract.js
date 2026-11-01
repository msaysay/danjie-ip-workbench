/** Shared StoryCue wizard and interview display rules. No Key values are kept here. */

export const FRAMEWORKS = [
  ['观点破题', '观点破题', '用不同判断开场，以原话和证据讲清道理'],
  ['四维信任', '四维信任', '兼顾破圈、人设、专业与转化'],
  ['方法直给', '方法直给', '讲清方法步骤，用具体例子帮助理解'],
  ['痛点解答', '痛点解答', '从客户问题讲到答案、依据与下一步'],
  ['情绪共鸣', '情绪共鸣', '从一个真实瞬间和感受切入'],
  ['人物故事', '人物故事', '用与业务有关的经历、选择和转折建立信任'],
  ['现场探访', '现场探访', '按客户关心的顺序串起可拍的现场'],
  ['决策问答', '决策问答', '围绕选择前的疑虑做一问一答'],
];

const FRAMEWORK_LABELS = new Set(FRAMEWORKS.map(item => item[1]));

export function frameworkLabel(value) {
  const text = String(value || '').trim();
  return FRAMEWORK_LABELS.has(text) ? text : '';
}

export const DESKTOP_COMMANDS = {
  connectWorkbuddy: 'npm run desktop:connect -- --host workbuddy',
  connectCodex: 'npm run desktop:connect -- --host codex',
  login: 'npm run desktop:login',
  doctor: 'npm run desktop:doctor',
};

export const TEXT_MODEL_EXAMPLE = {
  llmBaseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
  llmModel: 'doubao-seed-2-0-lite-260428',
};

export const WIZARD_STEPS = [
  {id: 'desktop', title: '连接电脑上的 WorkBuddy / Codex'},
  {id: 'speech', title: '豆包语音 Key'},
  {id: 'text', title: '文字模型'},
  {id: 'jev', title: 'Jev（可选）'},
  {id: 'done', title: '完成'},
];

export function startupCommands(directory) {
  const dir = (directory || 'StoryCue所在目录').replaceAll('"', '');
  const win = dir.replaceAll('/', '\\');
  return {
    windows: `cd /d "${win}" && set VOICE_RELAY_PORT=8866&& npm run dev`,
    mac: `cd "${dir}" && VOICE_RELAY_PORT=8866 npm run dev`,
    voiceRelayPort: '8866',
  };
}

export function publicSetup(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const bridge = raw.desktopBridge && typeof raw.desktopBridge === 'object' ? raw.desktopBridge : {};
  return {
    speechConfigured: !!raw.speechConfigured,
    textConfigured: !!raw.textConfigured,
    jevEnabled: !!raw.jevEnabled,
    llmBaseUrl: typeof raw.llmBaseUrl === 'string' ? raw.llmBaseUrl : '',
    llmModel: typeof raw.llmModel === 'string' ? raw.llmModel : '',
    desktopBridge: {
      configured: !!bridge.configured,
      host: bridge.host || null,
      model: bridge.model || null,
      verified: !!bridge.verified,
      entry: bridge.entry || '',
    },
  };
}

export function safeMessage(text, secrets) {
  let out = String(text || '请求失败');
  for (const secret of secrets || []) {
    if (typeof secret === 'string' && secret.length >= 8) out = out.split(secret).join('[redacted]');
  }
  return out;
}

export function stepCanTest(step, fields, status) {
  const setup = status?.setup;
  if (!status?.tokenReady) return false;
  if (step === 'desktop') return true;
  if (step === 'speech') return !!(fields.speechKey.trim() || setup?.speechConfigured);
  if (step === 'text') return !!(fields.llmBaseUrl.trim() && fields.llmModel.trim() && (fields.textKey.trim() || setup?.textConfigured));
  if (step === 'jev') return !fields.enableJev || !!(fields.jevKey.trim() || setup?.jevEnabled);
  return false;
}

export function formatInterview(interview) {
  if (!interview || interview.schema !== 'storycue.interview-export.v1') return null;
  const advice = interview.editingAdvice && typeof interview.editingAdvice === 'object' ? interview.editingAdvice : null;
  return {
    demo: !!interview.demo,
    framework: frameworkLabel(interview.framework),
    focus: interview.plan?.focus || '',
    questions: Array.isArray(interview.plan?.questions) ? interview.plan.questions.map(q => ({label: q.label || '', question: q.question || '', notes: q.notes || ''})) : [],
    entries: Array.isArray(interview.entries) ? interview.entries.filter(e => !e?.provisional).map(e => ({role: e.role || '', text: e.text || '', at: e.at || ''})) : [],
    mainline: advice?.mainline || '',
    clips: Array.isArray(advice?.clips) ? advice.clips : [],
    cautions: Array.isArray(advice?.cautions) ? advice.cautions : [],
    hasAdvice: !!advice,
  };
}
