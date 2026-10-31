"""Reuse completed Danjie homework behind one whole-script drafting action."""
from pathlib import Path
import hashlib,json,re
from datetime import datetime,timezone

VERSION='danjie-whole-script/1'
MODULES={'客群卡','三圈选题','当头一棒','以理服人','亮出绝活','指条明路','开场八式','人设卡','四行简介','乾坤大挪移','六脉神剑','一题多讲','写作要求'}
SOURCE_FILES=[
 '03/danjie-counterintuitive-opening-check063/SKILL.md',
 '04/danjie-evidence-guide/SKILL.md',
 '04/danjie-evidence-guide/assets/method-prompts.json',
 '05/owner-ip-muscle-words/SKILL.md',
 '05/owner-ip-muscle-words/references/output-schema.md',
 '06/danjie-five-endings-check012/SKILL.md',
 '07/danjie-eight-openings-final/references/generation.md',
]
RULES='''你在使用学员已经完成的蛋蛋作业写一篇完整口播，不是在重新主持采访。
先读同一人物、同一业务的现有客群、三圈选题、开头、支撑材料、绝活、收尾、人设与本轮修改要求；已有信息不再重复问。只在确实无法安全成稿时指出最小缺口。
后台依次安排四个作用，前台只交有衔接的整篇稿，不把四张卡简单粘贴，不念内部规则和核验过程：
1 开头：03当头一棒的必要条件/选择标准/结果方向三种反转，或07开场八式（当头一棒、追魂一问、引人入局、双锋对决、一剑定局、隔空点将、当场亮剑、欲擒故纵）。根据本题和现有材料选一种，不为反常识硬造旧认知。缺反向证据用“不等于”，不编“越做越坏”。故事缺原件可用明确假设；拍法不是已发生事件。
2 支撑：04以理服人，从有事、有数、有对比、有研究中选贴题的主路线，不硬塞四种。真事讲卡点/动作/变化；数字讲来源/口径/怎么算；对比讲比较对象/同等条件/实际差别；研究讲谁研究什么/怎么得出/边界。材料只是取材方向时，不改写成已经实测或研究证明；可以讲清一个待执行的检查/比较方法。
3 肌肉句：05亮出绝活，优先沿用学员已完成且允许公开的实力原句；我是谁→帮谁解决什么→做过多大规模→取得什么结果。至多3项相关数字，保留团队、参与、约、其中一例、收到反馈等归属和范围。它说明本人做过什么，不能替代观点证据。没有成绩数字就只用真实身份/职责，不制造业绩，也不把“我关注/我希望”冒充完整实力证明；缺口只记后台，不在口播念“缺证/待补”。
4 收尾：06指条明路只选一个落点：给入口、留动作、总结观点、留下记忆、接个问题。优先沿用本题已有收尾原句。只有已明确当前开放且可公开的服务、第一步和入口齐备，才能引导报名/私信领取；不编资料、名额、自动回复、优惠或下一条承诺。没有公开入口就用合适的一步动作、总结或问题，不能把转化简单等同于私信。
03/04/06按本题绑定，别的题成品只能参考方法，不能冒充本题已确认材料。05固定实力介绍可在同业务复用；08/09帮忙保持表达，不替代05成绩。10用于大众入口，11仅已有真实故事，12用于同题换讲法；不必每条全用。
原稿里的观点只是待核对候选；整稿确认不伪造各原生Skill的确认回执。课堂演练身份保持，不编造本人客户、结果或外部来源。本人长期要求与明确改稿意见优先。
比较两种做法时，先在内部、测试环境或脱敏草稿上比较；不得建议把未经事实核对的版本发给真实客户来观察返工。正式对外交付前，两种做法都须经过必要的事实核对。不要把“可能影响部分内容”说成“一处错就必然整份返工”，按真实影响范围说明。'''

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def source_contract(root):
 folder=Path(root)/'frozen-skills-v041';sources=[]
 for relative in SOURCE_FILES:
  p=folder/relative
  sources.append({'file':relative,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 return {'version':VERSION,'rules':RULES,'sources':sources}

def asset_time(a):
 try:
  d=datetime.fromisoformat(a.get('created_at','').replace('Z','+00:00'))
  if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
  return (d-datetime(1970,1,1,tzinfo=timezone.utc)).total_seconds()
 except (ValueError,TypeError):return 0

def writing_projection(asset,title=None):
 """Keep original text fields, discard presentation data and unrelated variants."""
 text=asset['content'];value=None
 try:value=json.loads(text.lstrip('\ufeff'))
 except (ValueError,TypeError):
  if Path(asset.get('name','')).suffix.lower()=='.html':
   from method_preview import scripts_in,LITERAL
   for attrs,body in scripts_in(text):
    try:
     if 'application/json' in attrs.lower():value=json.loads(body)
     else:
      match=LITERAL.search(body)
      if not match:continue
      value,_=json.JSONDecoder().raw_decode(body[match.end():])
     if isinstance(value,dict):break
    except ValueError:continue
   if not isinstance(value,dict):
    from html.parser import HTMLParser
    class Visible(HTMLParser):
     def __init__(self):super().__init__();self.skip=0;self.parts=[]
     def handle_starttag(self,tag,attrs):
      if tag in ['script','style']:self.skip+=1
     def handle_endtag(self,tag):
      if tag in ['script','style']:self.skip=max(0,self.skip-1)
     def handle_data(self,data):
      if not self.skip and data.strip():self.parts.append(data.strip())
    reader=Visible();reader.feed(text);return '\n'.join(reader.parts)
 if not isinstance(value,dict):return text
 result=dict(value)
 if isinstance(value.get('topics'),list):
  rows=value['topics'];matches=[x for x in rows if isinstance(x,dict) and title in [x.get('title'),x.get('question'),x.get('topic'),x.get('label')]] if title else []
  if matches:result['topics']=matches
  elif asset.get('module') in ['一题多讲','开场八式']:
   result.pop('topics');result['topic_variant_count']=len(rows)
   result['projection_notice']='本次只取共同背景；具体变体需按原成果中的完整题目匹配，不能当本题已确认材料。'
 if asset.get('module')=='六脉神剑' and isinstance(value.get('outlines'),list):
  result['outlines']=[{k:x[k] for k in ['model','event_scope','status','event_anchor','absence_reason','gaps','boundaries'] if k in x} for x in value['outlines']]
  result['projection_notice']='仅保留原事件状态、来源和边界。原固定采访题库是取材问题，不是已发生故事。'
 return json.dumps(result,ensure_ascii=False,separators=(',',':'))

def material_context(memory,topic_title=None,*,source_binding=True):
 grouped={}
 moment=asset_time
 for a in memory.get('assets',[]):
  if a.get('encoding')!='text' or a.get('module') not in MODULES:continue
  # Topic-specific cards remain separate, while multiple versions of the same card collapse.
  from method_preview import topic_binding
  bound_topic=topic_binding(a['content'],a['module'],a.get('topic','共用资料')) if source_binding else a.get('topic','共用资料')
  if source_binding and topic_title and bound_topic.endswith(('？','?')) and bound_topic!=topic_title and a['module'] in ['当头一棒','以理服人','指条明路','开场八式']:continue
  key=(a['module'],bound_topic)
  grouped.setdefault(key,[]).append(a)
 latest={}
 for key,items in grouped.items():
  newest=max(items,key=moment);batch=[a for a in items if moment(a)>=moment(newest)-2 and a.get('source')==newest.get('source')]
  # Native exports often emit JSON and multi-megabyte image-rich HTML milliseconds apart.
  # Prefer the structured companion in that same export, never an older card from another run.
  source=max(batch,key=lambda a:({'.json':3,'.md':2,'.txt':2,'.html':1}.get(Path(a.get('name','')).suffix.lower(),0),moment(a)))
  latest[key]={**source,'topic':key[1]}
 notes={}
 for note in memory.get('notes',[]):notes[note.get('category','voice')]=note
 result={'owner':memory['owner'],'business':memory['business'],'mode':memory['mode'],'current_assets':[{**{k:a.get(k) for k in ['id','name','module','topic','version','sha256']},'content':writing_projection(a,topic_title)} for a in latest.values()],'current_notes':[{'category':n.get('category'),'text':n['text']} for n in notes.values()]}
 if len(json.dumps(result,ensure_ascii=False))>160000:raise ValueError('已有作业文字较多，请让WorkBuddy先整理本次写稿材料；原件仍保留')
 return result

def request_context(root,memory,topic,feedback=(),references=(),*,source_binding=True):
 context={'method':source_contract(root),'memory':material_context(memory,topic.get('title'),source_binding=source_binding),'topic':{k:topic.get(k) for k in ['id','title','audience','needs']},'revision_requests':[{'direction':x.get('direction',''),'status':'待验证的改稿方向，不是客户事实'} for x in feedback],'references':[{'title':x.get('title',''),'url':x.get('url',''),'notes':x.get('notes','')} for x in references]}
 context['topic']['saved_revision_notes']=[h['note'] for h in topic.get('history',[]) if h.get('action')=='script' and h.get('note')][-6:]
 if topic.get('method_choices'):context['topic']['method_choices']=topic['method_choices']
 context['material_signature']=digest(context)
 return context

def homework_version(root,memory):return digest({'method':source_contract(root),'memory':material_context(memory)})

def handoff_format(profile_id,mode,version):
 return {'profile_id':profile_id,'mode':mode,'writing_material_version':version,'date':'运行当天的北京时间日期','topics':[{'title':'一个具体问题','audience':'讲给谁','reason':'为什么适合本次客户','needs':[1],'framework':[{'key':k,'label':label,'skill':skill,'text':'本题已经整理好的段落'} for k,label,skill in [('opening','开头','03或07'),('reason','支撑','04'),('identity','肌肉句或真实身份','05'),('ending','单一收尾','06')]],'prepared_script':{'script':'已经写好的完整口播，不是让用户再次拼四段','parts':[{'key':k,'text':'对应本稿段落'} for k in ['opening','reason','identity','ending']],'plan':{'opening_method':'实际采用的方法','proof_method':'实际采用的一种取材路线','proof_state':'method_only','muscle_state':'identity_only','muscle_gaps':['未提供的事实，只记后台'],'ending_method':'总结观点','source_shas':['当前作业版本.json中实际读过的文件sha256'],'public_entry_quotes':[]},'generated_by':'WorkBuddy按已有作业写稿'}}]}

def validate_result(result,context):
 if not isinstance(result,dict):raise ValueError('还没取得完整脚本，原稿已保留')
 script=result.get('script');parts=result.get('parts');plan=result.get('plan')
 if not isinstance(script,str) or not 80<=len(script.strip())<=20000 or not isinstance(parts,list) or [p.get('key') for p in parts]!=['opening','reason','identity','ending']:raise ValueError('整稿和写法还不完整，原稿已保留')
 if any(not isinstance(p.get('text'),str) or not p['text'].strip() or len(p['text'])>6000 for p in parts):raise ValueError('脚本中有一段尚未写好，原稿已保留')
 if not isinstance(plan,dict) or plan.get('proof_state') not in ['documented','method_only','hypothetical'] or plan.get('muscle_state') not in ['homework_sentence','identity_only']:raise ValueError('还没说明这稿用了哪些已有材料，原稿已保留')
 known={a['sha256'] for a in context['memory']['current_assets'] if a.get('sha256')}
 if not plan.get('source_shas') or any(sha not in known for sha in plan['source_shas']):raise ValueError('写稿引用与本次作业不一致，请接着当前资料重写')
 if plan.get('muscle_state')=='identity_only' and re.search(r'\d',parts[2]['text']):raise ValueError('身份句里出现了没有来源的成绩数字，原稿已保留')
 if plan.get('ending_method')=='给入口' and not plan.get('public_entry_quotes'):raise ValueError('还没有可公开的实际入口，不能编报名或私信领取')
 return {'version':VERSION,'material_signature':context['material_signature'],'script':script.strip(),'parts':parts,'plan':plan,'generated_by':str(result.get('generated_by','写作模型'))[:100]}

OUTPUT='''返回JSON：{script:"整篇自然口播，段落有衔接，无框架标题或后台说明",parts:[{key:"opening",label:"开头",skill:"03或07",text:"本稿实际开头"},{key:"reason",label:"支撑",skill:"04",text:"本稿支撑"},{key:"identity",label:"肌肉句或身份",skill:"05",text:"本稿本人介绍"},{key:"ending",label:"收尾",skill:"06",text:"本稿唯一收尾"}],plan:{opening_method:"实际选法",proof_method:"实际选法",proof_state:"documented|method_only|hypothetical",muscle_state:"homework_sentence|identity_only",muscle_gaps:[],ending_method:"五种之一",source_shas:["实际读取作业的sha256"],public_entry_quotes:[]}}。不要假装用户已确认，不在正文附采访问题或技术流程。'''
