import React, {useEffect, useRef} from 'react';
import {OPEN_HOST_NOTE, PASTE_FALLBACK, UNDERSTANDING_INTRO, copyHandoffMessage, prepareResultMessage, transcriptNote} from './publishHostContract.js';

export default function PublishUnderstanding({api, p, prepared, busy, running, jobs, save, act, setMessage, setModal, fileURL}) {
  const seen = useRef(null);
  const task = p?.publish_host_task;
  const waiting = task?.status === 'waiting';
  useEffect(() => {
    const job = (jobs || []).find(item => item.target === p?.id && item.kind === '理解视频并准备两平台发布信息');
    if (!job) return;
    const mark = job.id + ':' + job.state;
    if (seen.current === null) {
      seen.current = mark;
      return;
    }
    if (mark === seen.current) return;
    seen.current = mark;
    if (job.state === 'completed' && job.result?.handoff) setMessage(job.result.message);
    else if (job.state === 'completed' && job.result?.summary) setMessage('已经根据成片拟了一版。请核对原话和标题。不会自动发布。');
    else if (job.state === 'failed' && job.message) setMessage(job.message);
  }, [jobs, p?.id, setMessage]);
  async function prepare() {
    const saved = await save();
    if (!saved) return;
    const result = await api('/projects/' + p.id + '/prepare-delivery', 'POST', {});
    setMessage(prepareResultMessage(result));
  }
  async function copyTask() {
    const result = await api('/projects/' + p.id + '/publish-task', 'POST', {});
    let copied = false;
    try {
      await navigator.clipboard.writeText(result.prompt);
      copied = true;
    } catch {
      copied = false;
    }
    const text = copyHandoffMessage(result.host_label);
    setMessage(copied ? text : '没能写入剪贴板。任务文件已经放在成片旁边，可以打开写稿窗口后自己复制。' + OPEN_HOST_NOTE + PASTE_FALLBACK);
  }
  async function openHost() {
    const result = await api('/writing/host/open', 'POST', {host: task?.host || 'workbuddy'});
    setMessage(result.message || OPEN_HOST_NOTE);
  }
  async function syncHost() {
    const saved = await save();
    if (!saved) return;
    const result = await api('/projects/' + p.id + '/publish-understanding/sync', 'POST', {});
    setMessage(result.message || '已读回这一版文字。请对照成片核对，不会自动发布。');
  }
  return <section className="experience-section" aria-label="根据成片拟文字"><div className="publish-source-grid"><video controls preload="metadata" src={fileURL(p.output.file)}/><div><span className="eyebrow">可以让工作台先拟一版文字</span><h2>{prepared?.understanding ? '已经根据成片拟了一版' : '标题也可以自己写'}</h2><p>{prepared?.understanding?.summary || UNDERSTANDING_INTRO}</p><div className="row wrap"><button disabled={busy || running} onClick={() => act(prepare)}>{running ? '正在准备…' : '根据成片拟一版文字'}</button><button disabled={busy || running} onClick={() => act(copyTask)}>复制给 AI 整理文案</button><button disabled={busy || running} onClick={() => setModal({kind: 'import-copy', title: '粘贴 AI 写好的发布文字'})}>粘贴发布文字</button></div><small className="setting-help">{transcriptNote(prepared?.transcript_source?.kind)}{(waiting || !prepared?.understanding) ? OPEN_HOST_NOTE : ''}</small></div></div>{waiting && <div className="publish-host-handoff" role="status"><strong>交给{task.host_label || 'WorkBuddy 或 Codex'}看这条成片</strong><p>{task.message}</p>{task.video && <p className="setting-help">成片文件：<code className="storycue-command">{task.video}</code></p>}<div className="row wrap"><button type="button" disabled={busy || running} onClick={() => act(openHost)}>打开写稿窗口</button><button type="button" disabled={busy || running} onClick={() => act(copyTask)}>复制给写稿 AI</button><button type="button" className="primary" disabled={busy || running} onClick={() => act(syncHost)}>读回这一版文字</button></div><p className="setting-help">{OPEN_HOST_NOTE}读回只保存草稿。抖音和视频号的扫码在上面的账号一栏，两件事分开。</p></div>}{prepared?.transcript && <details><summary>看看原话，以及还要核对的地方</summary><p>{prepared.transcript}</p><ul>{prepared.understanding?.limits?.map(line => <li key={line}>{line}</li>)}</ul></details>}</section>;
}