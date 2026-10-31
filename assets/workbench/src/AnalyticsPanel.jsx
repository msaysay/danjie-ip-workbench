import React,{useEffect,useRef,useState} from 'react';
import {RefreshCw,Download,ExternalLink} from 'lucide-react';

const BASE=location.protocol+'//127.0.0.1:'+(Number(location.port||8766)+4)+'/bridge';
const ACTION={doctor:'离线检查',acknowledge:'使用前确认',login:'专用登录',sync:'作品列表同步',details:'作品详情同步',export:'准备快照',import:'导入快照'};
const STATUS={completed:'已完成',partial:'部分数据',success:'已完成',logged_in:'已登录',login_required:'需要登录',verification_required:'需要验证',user_action_required:'需要处理'};
export default function AnalyticsPanel({refreshSignal,onRefresh,onChooseLifetime,notify}){
 const [state,setState]=useState(null),[preview,setPreview]=useState(null),[notice,setNotice]=useState(null),[confirmation,setConfirmation]=useState(''),[accepted,setAccepted]=useState(false),[busy,setBusy]=useState(false);
 const token=useRef('');
 async function request(path,body){const r=await fetch(BASE+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Analytics-Token':token.current}:{},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok)throw Error(data.detail||'数据模块请求失败');return data}
 async function load(){try{const d=await request('/state');token.current=d.token;setState(d)}catch{setState({unavailable:true})}}
 useEffect(()=>{load()},[refreshSignal]);
 async function action(name,body={}){setBusy(true);try{await request('/actions/'+name,body);await onRefresh();await load();if(name==='import')onChooseLifetime();notify('数据任务已提交，结果见运行记录')}catch(e){notify(e.message)}finally{setBusy(false)}}
 const running=state?.jobs?.some(j=>j.state==='running');const blocked=busy||running||!state?.installed;
 const ack=state?.status?.acknowledged;
 async function viewPreview(){try{setPreview(await request('/preview'))}catch(e){notify(e.message)}}
 return <section className="analytics-panel"><div className="row spread"><div><h3>抖音数据连接</h3><p>独立的本机浏览器数据模块；需要单独登录，只读取本人账号可见内容。</p></div><span className="status">{state?.unavailable?'连接服务未启动':state?.status?.state||'正在检查连接'}</span></div>
 {state?.unavailable?<p className="muted small">重新打开启动工作台入口可启动本机数据连接。视频号目前仍使用后台导出表导入。</p>:<>
 <div className="row wrap analytics-controls"><button disabled={blocked} onClick={()=>action('doctor')}><RefreshCw size={14}/>离线检查</button>
 {!ack&&<button disabled={blocked} onClick={async()=>{try{setNotice(await request('/notice'))}catch(e){notify(e.message)}}}>阅读并启用</button>}
 <button disabled={blocked||!ack} onClick={()=>action('login')}>专用登录</button><button disabled={blocked||!ack} onClick={()=>action('sync')}>同步作品列表</button><button disabled={blocked||!ack} onClick={()=>action('details')}>最近 5 条详情</button><button disabled={blocked} onClick={()=>action('export')}><Download size={14}/>准备快照</button><button disabled={blocked} onClick={viewPreview}>查看导入预览</button>
 </div>
 <p className="muted small">{ack?'上游使用前确认已记录。':'尚未启用浏览器数据读取。离线诊断通过不代表已登录或已采集。'} 视频号目前仍使用后台导出表导入。</p>
 {state?.status?.last_result&&<p className="muted small">最近动作：{ACTION[state.status.last_action]||state.status.last_action} · {STATUS[state.status.last_result.login_status||state.status.last_result.status]||'见运行记录'}</p>}
 {running&&<p className="running">数据任务正在运行，保留原任务等待结果。</p>}
 {preview&&<div className="analytics-preview"><div className="row spread"><strong>快照预览 · {preview.total} 行</strong><button className="primary" disabled={blocked||!preview.total} onClick={()=>action('import')}>导入最近 20 条作品</button></div><p className="muted small">{preview.note} 缺失值不补零；没有平台作品编号时使用明确标记的本地身份。</p>
 <div className="table-wrap"><table><thead><tr><th>作品</th><th>播放</th><th>点赞</th><th>来源</th><th>采集时间</th></tr></thead><tbody>{preview.rows.slice(0,5).map((r,i)=><tr key={i}><td>{r.title}</td><td>{r.views??'—'}</td><td>{r.likes??'—'}</td><td>{{browser_list:'作品列表',browser_detail:'作品详情'}[r.snapshot_source]||r.snapshot_source}</td><td>{r.observed_at}</td></tr>)}</tbody></table></div></div>}
 </>}
 {notice&&<div className="modal-backdrop"><section className="modal large" role="dialog" aria-modal="true" aria-label="数据模块使用前确认"><div className="row spread"><h2>数据模块使用前确认</h2><button onClick={()=>setNotice(null)}>关闭</button></div><p className="muted">以下是所选上游工具的说明。该工具是非官方浏览器自动化，可能触发平台风控；确认记录不能替代必要授权。</p><pre className="document">{notice.text}</pre><a href={notice.source} target="_blank" rel="noreferrer">查看上游原文 <ExternalLink size={13}/></a><label className="analytics-accept"><input type="checkbox" checked={accepted} onChange={e=>setAccepted(e.target.checked)}/>我已阅读工具说明，并确认拥有所需授权。</label><label>输入“我已阅读并确认”<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} autoComplete="off"/></label><div className="modal-footer"><button onClick={()=>setNotice(null)}>暂不启用</button><button className="primary" disabled={!accepted||confirmation!=='我已阅读并确认'||busy} onClick={async()=>{await action('acknowledge',{confirmation});setNotice(null)}}>记录确认</button></div></section></div>}
 </section>
}
