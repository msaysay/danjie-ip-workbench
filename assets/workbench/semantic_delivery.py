"""Reuse a transcript only when it is tied to the exact finished-video bytes.

Offline speech recognition stays optional. A missing faster_whisper install, or a
workbench model that is not connected, is handled by the writing-host handoff.
"""
import hashlib,json,os,shutil
from workflow_api import call_model

REUSABLE_KINDS=['existing_exact_video','offline_asr','host_understanding']

class AsrUnavailable(RuntimeError):
 """Offline speech recognition cannot run for this video."""

def model_connected():
 return bool(os.getenv('WORKBENCH_MODEL_BASE_URL') and os.getenv('WORKBENCH_MODEL'))

def whisper_available():
 try:
  import faster_whisper  # noqa: F401
  return True
 except ImportError:
  return False

def _cache_path(core,sha):
 return core.DATA/'video-transcripts'/(sha+'.json')

def _read_transcript_cache(cache,sha):
 if not cache.exists():return None
 row=json.loads(cache.read_text(encoding='utf-8'));speech=row.get('transcript','')
 if row.get('video_sha256')!=sha or hashlib.sha256(speech.encode()).hexdigest()!=row.get('transcript_sha256'):raise ValueError('已保存转写的校验不一致，请先保留原件核对，不覆盖它')
 return speech,{**row['source'],'cache_reused':True}

def find_existing_transcript(core,p):
 sha=p['output']['sha256']
 # Final render with edits cannot borrow the unedited source transcript.
 for other in core.listing('project'):
  if other.get('media',{}).get('sha256')==sha and other.get('segments'):
   rows=[{'start':s.get('start'),'end':s.get('end'),'text':s['text']} for s in other['segments'] if s.get('text')]
   if rows:return '。'.join(s['text'].strip('。') for s in rows),{'kind':'existing_exact_video','project_id':other['id'],'title':other['title'],'video_sha256':sha,'segments':rows}
 for other in core.listing('project'):
  old=other.get('publish_preparation') or {}
  if old.get('video_sha256')==sha and old.get('transcript') and old.get('transcript_source',{}).get('kind') in REUSABLE_KINDS:
   return old['transcript'],old['transcript_source']
 return _read_transcript_cache(_cache_path(core,sha),sha)

def transcribe_offline(core,p):
 sha=p['output']['sha256'];cache=_cache_path(core,sha)
 os.environ['HF_HUB_OFFLINE']='1'
 try:
  from faster_whisper import WhisperModel
 except ImportError as e:
  raise AsrUnavailable('本机没有 faster_whisper') from e
 with core.ASR_LOCK:
  previous=_read_transcript_cache(cache,sha)
  if previous:return previous
  try:
   segments,_=WhisperModel('small',device='cpu',compute_type='int8',local_files_only=True).transcribe(str(core.DATA/p['output']['file']),language='zh')
  except Exception as e:
   raise AsrUnavailable('离线听写这次没有跑起来') from e
  rows=[{'start':s.start,'end':s.end,'text':s.text.strip()} for s in segments if s.text.strip()]
  if not rows:raise ValueError('没有识别到语音。请补充本片的讲稿或文字说明后再准备发布')
  speech='。'.join(s['text'].strip('。') for s in rows);origin={'kind':'offline_asr','video_sha256':sha,'segments':rows,'needs_review':True}
  cache.parent.mkdir(exist_ok=True)
  with cache.open('x',encoding='utf-8') as f:json.dump({'video_sha256':sha,'transcript_sha256':hashlib.sha256(speech.encode()).hexdigest(),'transcript':speech,'source':origin,'created':core.now()},f,ensure_ascii=False,indent=2)
  return speech,origin

def locate_transcript(core,p):
 found=find_existing_transcript(core,p)
 if found:return found
 if not whisper_available():raise AsrUnavailable('本机没有 faster_whisper')
 return transcribe_offline(core,p)

def local_path_ready(core,p):
 """True when this machine can draft copy without the writing host."""
 found=find_existing_transcript(core,p)
 connected=model_connected()
 if found and connected:return True,'transcript'
 if not connected:return False,'model' if (found or whisper_available()) else 'both'
 if whisper_available():return True,'asr'
 return False,'asr'

def _frames(core,ident,source,out,folder):
 sha=out['sha256'];frames=[]
 for i,at in enumerate([min(2,out['duration']/4),out['duration']/2,max(0,out['duration']-1)]):
  f=folder/f'frame-{sha[:12]}-{i}-{round(at*1000)}.jpg'
  if not f.exists():core.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',str(at),'-i',source,'-frames:v','1','-q:v','2','-y',f])
  frames.append({'file':f.relative_to(core.DATA).as_posix(),'at':round(at,2)})
 return frames

def commit_understanding(core,ident,speech,origin,analysis,generated_by,basis,require_frames=True,preserve_cover=False):
 p=core.get('project',ident);out=p['output'];revision=p['revision'];source=core.DATA/out['file'];folder=core.project_dir(ident)/'publication';folder.mkdir(exist_ok=True)
 sha=out['sha256'];transcript_sha=hashlib.sha256(speech.encode()).hexdigest()
 analysis=dict(analysis)
 if not isinstance(analysis.get('summary'),str) or not all(k in analysis.get('platform_copy',{}) for k in ['douyin','tencent']):raise ValueError('视频理解结果不完整，原有发布信息没有被覆盖')
 analysis.update(video_sha256=sha,transcript_sha256=transcript_sha,generated_by=generated_by,created=core.now())
 analysis_dir=core.DATA/'video-understanding';analysis_dir.mkdir(exist_ok=True)
 (analysis_dir/(sha+'.json')).write_text(json.dumps(analysis,ensure_ascii=False,indent=2),encoding='utf-8')
 try:frames=_frames(core,ident,source,out,folder)
 except (OSError,RuntimeError):
  if require_frames:raise
  frames=list((p.get('publish_preparation') or {}).get('frames') or [])
 manifest_path=core.DATA/'cover-designs'/sha/'manifest.json';manual=p.get('cover_studio')
 prefer_manual=bool(manual and manual.get('kind')=='video_frame' and manual.get('video_sha256')==sha and all((core.DATA/manual.get(k,'missing')).is_file() for k in ['portrait','landscape','selected_frame']))
 manifest=dict(manual) if prefer_manual else json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else None
 if manifest and not prefer_manual:
  public=folder/('design-v'+str(manifest.get('version',1)));public.mkdir(exist_ok=True);manifest=dict(manifest)
  for key in ['selected_frame','portrait','landscape','reference','prompt_file']:
   original=(core.DATA/manifest[key]).resolve();cache_root=(core.DATA/'cover-designs'/sha).resolve()
   if not original.is_relative_to(cache_root) or not original.is_file():raise ValueError('封面参考原件无法核对，未替换现有资料')
   destination=public/original.name
   if destination.exists() and hashlib.sha256(destination.read_bytes()).digest()!=hashlib.sha256(original.read_bytes()).digest():raise ValueError('项目中的封面有了其他修改，请保留并另存新版本')
   if not destination.exists():shutil.copy2(original,destination)
   manifest[key]=destination.relative_to(core.DATA).as_posix()
  (public/'design-reference.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 selected=(p.get('publish_preparation') or {}).get('selected_frame') or (frames[0] if frames else None)
 if manifest and selected:
  selected_path=(core.DATA/selected['file']).resolve();ref=(core.DATA/manifest['selected_frame']).resolve()
  if not selected_path.is_relative_to(core.DATA.resolve()) or not ref.is_relative_to(core.DATA.resolve()) or not selected_path.is_file() or not ref.is_file() or hashlib.sha256(selected_path.read_bytes()).digest()!=hashlib.sha256(ref.read_bytes()).digest():manifest=None
 copy=json.loads(json.dumps(p.get('platform_copy',{})))
 for platform in ['douyin','tencent']:
  previous=copy.get(platform,{});draft=analysis['platform_copy'][platform]
  copy[platform]={**previous,**draft,'schedule':previous.get('schedule','')}
  if manifest and manifest.get('video_sha256')==sha and (prefer_manual or manifest.get('transcript_sha256')==transcript_sha):
   copy[platform].update(cover=manifest['portrait'],cover_landscape=manifest['landscape'])
 if preserve_cover:
  for platform in ['douyin','tencent']:
   old=(p.get('platform_copy') or {}).get(platform) or {};row=dict(copy.get(platform) or {})
   for key in ['cover','cover_landscape','schedule']:
    if key in old:row[key]=old[key]
    elif key!='schedule':row.pop(key,None)
   if 'schedule' in old:row['schedule']=old['schedule']
   copy[platform]=row
 current=core.get('project',ident)
 if current.get('revision')!=revision:raise ValueError('整理过程中你又修改了信息，生成结果已保留；请核对后再次准备，不覆盖刚才的手动修改')
 evidence={'created':core.now(),'basis':basis,'video_sha256':sha,'transcript_sha256':transcript_sha,'transcript':speech,'transcript_source':origin,'understanding':analysis,'frames':frames,'selected_frame':selected,'cover_design':manifest,'cover_state':('video_frame' if prefer_manual else 'generated') if manifest else 'needs_generation'}
 if preserve_cover:
  previous_prep=p.get('publish_preparation') or {}
  if previous_prep.get('cover_state'):
   evidence['cover_state']=previous_prep.get('cover_state');evidence['cover_design']=previous_prep.get('cover_design')
   if previous_prep.get('selected_frame'):evidence['selected_frame']=previous_prep['selected_frame']
   if previous_prep.get('frames') and not frames:evidence['frames']=previous_prep['frames']
 core.patch('project',ident,{'platform_copy':copy,'publish_preparation':evidence,'publish_host_task':None})
 return {'transcript_reused':origin.get('kind')=='existing_exact_video','transcript_source':origin.get('kind'),'summary':analysis['summary'],'covers':evidence['cover_state']}

def prepare(core,ident):
 p=core.get('project',ident);out=p['output']
 speech,origin=locate_transcript(core,p);sha=out['sha256'];transcript_sha=hashlib.sha256(speech.encode()).hexdigest()
 analysis_dir=core.DATA/'video-understanding';analysis_dir.mkdir(exist_ok=True);cache=analysis_dir/(sha+'.json')
 analysis=json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else None
 if not analysis or analysis.get('transcript_sha256')!=transcript_sha:
  try:analysis=call_model('理解这条视频的转写。只表达本片实际讲到的内容。返回 {summary,points:[字符串],limits:[字符串],platform_copy:{douyin:{title,desc,tags},tencent:{title,short_title,desc,tags}}}。抖音标题直白吸引人，视频号标题清楚，short_title为7到15个字，tags是逗号分隔的话题。视频只是预告或开场就明确写预告，不捏造教程、成果、数字。',{'transcript':speech,'duration':out['duration']})
  except ValueError as e:raise ValueError('已取得本片转写。'+('音频识别结果已单独保存，下次会先复用。' if origin['kind']=='offline_asr' else '')+str(e)) from None
 return commit_understanding(core,ident,speech,origin,analysis,os.getenv('WORKBENCH_MODEL') or '','先核对同一视频已有转写，再理解本片内容。')
