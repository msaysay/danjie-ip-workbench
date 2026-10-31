"""Danjie method library, explicit topic handoff, and scoped AI artifact delivery."""
import base64,hashlib,html,json,mimetypes,re
from pathlib import Path
from fastapi import Request,HTTPException
from method_preview import preview,candidates,scripts_in,trusted_runtime,declared_modes,topic_binding,source_strings
from danjie_writing import request_context,validate_result,homework_version,asset_time
from memory_limits import MAX_PROFILE_BYTES

METHODS=[('01','六维目标客户卡','客群卡','shared','先读懂你要服务的客户'),('08','六维人设卡','人设卡','shared','接着你本人已经做过的人设'),('09','四行简介','四行简介','shared','看看账号介绍怎么表达'),('02','三圈选题','三圈选题','fumo','点方向、处境和情境，找到要讲的问题'),('03','当头一棒','当头一棒','fumo','同一个题，看看怎样讲出判断'),('07','开场八式','开场八式','fumo','从八种开头中挑贴题的讲法'),('04','以理服人','以理服人','fumo','看看用什么事情、数字或对比来说明'),('05','亮出绝活','亮出绝活','fumo','沿用已经完成的本人实力介绍'),('06','指条明路','指条明路','fumo','给这条内容选一个清楚的收尾'),('10','乾坤大挪移','乾坤大挪移','qiankun','从客户、相关人和大众话题之间找连接'),('12','一题多讲','一题多讲','qiankun','同一题换关注点、问法和情境'),('11','六脉神剑','六脉神剑','six','接着已有的真实故事材料找表达')]

def attach(app,core):
 def active(expected=None):
  pid=core.WORKFLOW['settings']().get('profile_id')
  if not pid or (expected and expected!=pid):raise HTTPException(409,'本次业务有变化，请重新打开你的成果')
  p=core.get('project',pid);m=next((x for x in p.get('sources',[]) if x.get('kind')=='business_memory'),None)
  if not m:raise HTTPException(409,'先在设置里选择已经做过作业的业务')
  return p,m
 def asset(ident,expected_sha=None):
  p,m=active();a=next((a for a in m['assets'] if a['id']==ident),None)
  if not a:raise HTTPException(404,'这份成果不在本次业务里')
  raw=a['content'].encode('utf-8') if a['encoding']=='text' else base64.b64decode(a['content'],validate=True)
  if hashlib.sha256(raw).hexdigest()!=a['sha256'] or (expected_sha and a['sha256']!=expected_sha):raise HTTPException(409,'成果已有新版本，请重新打开再选')
  return p,m,a,raw
 def state_key(pid,aid):return core.digest({'profile':pid,'asset':aid})[:24]
 def last_selection(pid,aid):return next((x for x in core.listing('method_selection') if x['id']==state_key(pid,aid)),None)
 @app.get('/api/methods')
 def library():
  try:p,m=active()
  except HTTPException:return {'available':False,'methods':[],'profile':None}
  entries=[]
  for step,name,module,group,scene in METHODS:
   found=sorted([a for a in m['assets'] if a['module']==module],key=asset_time,reverse=True)
   readable=[a for a in found if a['encoding']=='text'];htmls=[a for a in readable if a['name'].lower().endswith('.html')];chosen=htmls[0] if htmls else readable[0] if readable else found[0] if found else None
   interactive=bool(chosen and chosen['encoding']=='text' and any('application/json' not in attrs.lower() and trusted_runtime(body,core.ROOT) for attrs,body in scripts_in(chosen['content'])))
   entries.append({'step':step,'name':name,'module':module,'group':group,'scene':scene,'state':'interactive' if interactive else 'card' if htmls else 'readable' if readable else 'archived' if found else 'missing','primary_id':chosen['id'] if chosen else None,'asset_count':len(found),'versions':[{'id':a['id'],'name':a['name'],'topic':a['topic'],'sha256':a['sha256'],'version':a['version'],'updated':a['created_at']} for a in found[:15]]})
  return {'available':True,'profile':{'id':p['id'],'owner':m['owner'],'business':m['business'],'mode':m['mode']},'methods':entries,'last_choice':next((x for x in core.listing('method_choice') if x['profile_id']==p['id']),None)}
 @app.get('/api/methods/assets/{ident}')
 def read_asset(ident:str):
  p,m,a,raw=asset(ident);suffix=Path(a['name']).suffix.lower();result={'profile_id':p['id'],'id':a['id'],'name':a['name'],'module':a['module'],'sha256':a['sha256'],'version':a['version'],'topic':a['topic'],'mode':m['mode'],'candidates':[],'selection':last_selection(p['id'],a['id'])}
  if a['encoding']=='text':
   if suffix=='.html':result.update(preview(a['content'],core.ROOT,a['id'],a['module']));result['candidates']=candidates(a['content'])
   else:result.update(text=a['content'],interactive=False);result['candidates']=candidates(a['content'],a['module'])
  elif suffix in ['.png','.jpg','.jpeg']:result.update(image='data:'+a['mime']+';base64,'+base64.b64encode(raw).decode(),interactive=False)
  else:result.update(text='原件已经保存。请让WorkBuddy把这份成果整理为可读卡片后接回。',interactive=False)
  return result
 @app.get('/api/methods/ai-instructions')
 def ai_instructions():
  p,m=active();helper=str(core.ROOT/'workbuddy_publish_method.py');manifest={'profile_id':p['id'],'owner':m['owner'],'business':m['business'],'mode':m['mode'],'module':'三圈选题','topic':'共用资料','source_dir':'本次原版Skill实际结果目录','files':['实际HTML文件名','实际交接JSON文件名']}
  prompt='请把我已经做好的蛋蛋成果接回本机工作台，不重新采访。先核对同一人物、同一业务和资料性质，优先用原版Skill导出的HTML和交接JSON；原件与旧版保留。如果已有13号总装项目，直接读取project.json中登记的公开成果，按模块接回，不要求我重新找文件，也不读取runtime私有采访状态。逐项接回三圈选题、开头、支撑、绝活、收尾、人设、简介、乾坤连线、一题多讲和故事等实际已有成果。不要把安装包、密钥、Cookie或私有采访状态上传。\n\n每次只在本次结果目录里写一个接回清单，按实际成果修改module、topic、source_dir和files，不用学员填JSON：\n'+json.dumps(manifest,ensure_ascii=False,indent=2)+'\n\n然后使用本机已有Python执行：\npython "'+helper+'" --manifest "本次接回清单.json"\n\n读取返回并在“蛋解方法”页核对入口。没有生成的成果如实留缺口，不用其他人的演示或静态图冒充交互成品。导入不代表本人确认选题；留给本人在页面点“就写这题”。只接回文件，不自动发布或投流。'
  return {'profile_id':p['id'],'text':prompt}
 def checked_selection(d):
  p,m=active(d.get('profile_id'));_,_,a,_=asset(str(d.get('asset_id','')),d.get('asset_sha'));title=str(d.get('title','')).strip()
  pool=candidates(a['content'],a['module']) if a['encoding']=='text' else []
  if not title or len(title)>400 or not any(c['title']==title for c in pool):raise HTTPException(400,'请从这张成果里选一个已经生成的题目；新中心需先由AI补出选题')
  state=d.get('state') or {}
  if not isinstance(state,dict) or len(json.dumps(state,ensure_ascii=False))>12000:raise HTTPException(400,'本次选择需要重新核对')
  clean={k:str(state[k])[:limit] for k,limit in [('center',100),('chain',1000),('candidate_id',80),('opening',1500),('method',150)] if isinstance(state.get(k),str)}
  if isinstance(state.get('cells'),list):clean['cells']=[{'axis':x['axis'],'index':x['index']} for x in state['cells'][:24] if isinstance(x,dict) and isinstance(x.get('axis'),int) and isinstance(x.get('index'),int) and 0<=x['axis']<20 and 0<=x['index']<250]
  if isinstance(state.get('controls'),list):clean['controls']=[x for x in state['controls'][:20] if isinstance(x,dict) and set(x).issubset({'id','data','label'}) and len(json.dumps(x,ensure_ascii=False))<1600]
  clean['topic']=title
  state=clean
  return p,m,a,title,state
 @app.post('/api/methods/selection')
 async def selection(r:Request):
  p,m,a,title,state=checked_selection(await r.json())
  return core.put('method_selection',{'id':state_key(p['id'],a['id']),'profile_id':p['id'],'asset_id':a['id'],'asset_sha':a['sha256'],'title':title,'state':state,'confirmed':False,'updated_at':core.now()})
 @app.post('/api/methods/confirm-topic')
 async def confirm(r:Request):
  d=await r.json();p,m,a,title,state=checked_selection(d)
  with core.LOCK:
   if core.get('project',p['id'])['revision']!=p['revision']:raise HTTPException(409,'资料刚有更新，请重新核对这道题')
   existing=next((t for t in core.listing('writing_topic') if t.get('profile_id')==p['id'] and t['title']==title),None)
   ident=existing['id'] if existing else core.uid();choice={'module':a['module'],'asset_id':a['id'],'asset_sha':a['sha256'],'title':title,'state':state}
   if not existing:
    topic={'id':ident,'profile_id':p['id'],'title':title,'audience':'沿用本次客户卡','reason':'从'+a['module']+'中由本人选定','needs':[],'framework':[{'key':k,'label':label,'skill':skill,'text':''} for k,label,skill in [('opening','开头','03或07'),('reason','支撑','04'),('identity','本人实力','05'),('ending','收尾','06')]],'confirmed':True,'stage':'topic','script':'','history':[],'demo':m['mode']=='fictional_demo','origin':'method_choice','method_choices':[choice],'created':core.now()}
    ready=next((x for x in core.listing('method_draft') if x.get('profile_id')==p['id'] and x['title']==title and x.get('writing_material_version')==homework_version(core.ROOT,m)),None)
    if ready:
     ctx=request_context(core.ROOT,m,topic,[x for x in core.listing('writing_feedback') if x.get('profile_id')==p['id']][:8],[x for x in core.listing('idea') if x.get('profile_id')==p['id']][:8]);topic['prepared_script']=validate_result(ready['result'],ctx)
    core.put('writing_topic',topic)
   elif existing['stage'] in ['topic','framework']:
    # A daily suggestion may already exist before the learner picks an opening.
    # Keep its prepared draft as a recoverable artifact, but bind the writing
    # request to the actual latest choice. Its old signature must not silently
    # authorize a draft that was prepared for a different opening.
    old_choices=existing.get('method_choices',[])
    choices=[x for x in old_choices if x.get('module')!=choice['module']]+[choice]
    changes={'method_selected':True,'confirmed':True,'method_choices':choices}
    prepared=existing.get('prepared_script')
    if choices!=old_choices and isinstance(prepared,dict) and prepared.get('material_signature'):
     feedback=[x for x in core.listing('writing_feedback') if x.get('profile_id')==p['id']][:8];refs=[x for x in core.listing('idea') if x.get('profile_id')==p['id']][:8]
     prior_contexts=[request_context(core.ROOT,m,existing,feedback,refs,source_binding=b) for b in [True,False]]
     norm=lambda value:re.sub(r'\s+','',str(value)).rstrip('。！？!?')
     opening=state.get('opening','');first=next((x.get('text','') for x in prepared.get('parts',[]) if x.get('key')=='opening'),'')
     same_opening=bool(norm(opening) and norm(first).startswith(norm(opening)) and any(norm(opening)==norm(value) for value in source_strings(a['content'])))
     topic_only=not opening and not state.get('method')
     if prepared['material_signature'] in [c['material_signature'] for c in prior_contexts] and (same_opening or topic_only):
      try:
       updated_context=request_context(core.ROOT,m,{**existing,**changes},feedback,refs)
       changes['prepared_script']=validate_result(prepared,updated_context)
       changes['prepared_binding_note']='同一当前资料、同题且开头与原卡一致；只更新选择来源，保留原生成者。'
      except ValueError:pass
    if choices!=old_choices:
     changes['history']=existing.get('history',[])+[{'at':core.now(),'action':'method_choice','note':'已保存这次选题和讲法，写稿沿用本次选择；旧预备稿保留。','before':{'method_choices':old_choices}}]
    core.patch('writing_topic',ident,changes)
   # Existing drafts and approved scripts remain intact; source choice is recorded separately.
   core.put('method_choice',{'id':core.uid(),'profile_id':p['id'],'topic_id':ident,'choice':choice,'created':core.now(),'topic_confirmed':True,'script_confirmed':False})
   core.put('method_selection',{'id':state_key(p['id'],a['id']),'profile_id':p['id'],'asset_id':a['id'],'asset_sha':a['sha256'],'title':title,'state':state,'confirmed':False,'updated_at':core.now()})
  return {'topic_id':ident,'title':title,'profile_id':p['id'],'existing_script_preserved':bool(existing),'auto_draft':not existing or existing['stage'] in ['topic','framework']}
 @app.post('/api/methods/artifacts')
 async def import_artifacts(r:Request):
  d=await r.json();p,m=active(d.get('profile_id'))
  if any(d.get(k)!=m[k] for k in ['owner','business','mode']):raise HTTPException(409,'这批成果和当前业务不一致，原资料没有改动')
  module=str(d.get('module',''));topic=str(d.get('topic','共用资料'))[:200];files=d.get('files',[])
  if module not in [x[2] for x in METHODS] or not isinstance(files,list) or not 1<=len(files)<=12:raise HTTPException(400,'请选择一种蛋解成果，一批最多12个文件')
  memory=json.loads(json.dumps(m));count=0
  for f in files:
   if not isinstance(f,dict) or not isinstance(f.get('content'),str):raise HTTPException(400,'文件内容未读完整')
   name=Path(str(f.get('name','')).replace('\\','/')).name;ext=Path(name).suffix.lower()
   if ext not in ['.html','.json','.md','.txt','.png','.jpg','.jpeg','.pdf','.docx'] or f.get('encoding') not in ['text','base64']:raise HTTPException(400,'请接入原版HTML、文字、图片或文档成果')
   try:raw=str(f.get('content','')).encode('utf-8') if f['encoding']=='text' else base64.b64decode(f.get('content',''),validate=True)
   except (ValueError,TypeError):raise HTTPException(400,'文件内容未读完整')
   digest=hashlib.sha256(raw).hexdigest()
   if len(raw)>6*1024*1024 or f.get('sha256')!=digest:raise HTTPException(400,'文件过大或内容有变化，请重新读取原件')
   if ext=='.json':
    try:obj=json.loads(raw.decode('utf-8-sig'))
    except (ValueError,UnicodeError):raise HTTPException(400,'这份JSON成果无法读取')
    if isinstance(obj,dict) and obj.get('mode') in ['real','fictional_demo'] and obj['mode']!=m['mode']:raise HTTPException(409,'课堂演练不能变成本人真实成果')
   if ext=='.html':
    if any(mode!=m['mode'] for mode in declared_modes(raw.decode('utf-8-sig'))):raise HTTPException(409,'这张交互卡与本次业务的资料性质不一致')
   bound_topic=topic_binding(f['content'],module,topic) if f['encoding']=='text' else topic
   if any(x['sha256']==digest and x['module']==module and (topic_binding(x['content'],module,x['topic']) if x['encoding']=='text' else x['topic'])==bound_topic for x in memory['assets']):continue
   version=1+max([x['version'] for x in memory['assets'] if (x['name'],x['module'],x['topic'])==(name,module,bound_topic)]or[0])
   memory['assets'].append({'id':core.uid(),'name':name,'module':module,'topic':bound_topic,'size':len(raw),'sha256':digest,'mime':mimetypes.guess_type(name)[0]or'application/octet-stream','encoding':f['encoding'],'content':f['content'],'version':version,'created_at':core.now(),'review':'pending','source':'AI接回蛋解成品'});count+=1
  if len(json.dumps(memory,ensure_ascii=False).encode())>MAX_PROFILE_BYTES:raise HTTPException(400,'本次业务资料超过64MB，请保留原件并按业务分开')
  with core.LOCK:
   if core.get('project',p['id'])['revision']!=p['revision']:raise HTTPException(409,'已有成果刚有变化，请重新接入，旧版保留')
   if count:core.patch('project',p['id'],{'sources':[memory if x.get('kind')=='business_memory' else x for x in p['sources']]})
  return {'imported':count,'profile_id':p['id'],'note':'已接回成果，旧版保留；文件里的确认标记不会替本人确认选题或脚本。'}
 return {'library':library,'read_asset':read_asset}
