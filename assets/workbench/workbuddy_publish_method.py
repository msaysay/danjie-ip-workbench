"""Publish explicitly listed original Skill outputs to this local learner workbench."""
import argparse,base64,hashlib,json,sys
from pathlib import Path
from workbuddy_sync import LocalHTTP,BASE

def publish(manifest):
 manifest=Path(manifest).resolve();d=json.loads(manifest.read_text(encoding='utf-8-sig'));folder=Path(d['source_dir']).resolve()
 if not folder.is_dir() or folder.is_symlink() or getattr(folder,'is_junction',lambda:False)():raise ValueError('请指定本次Skill结果目录')
 packet={k:d[k] for k in ['profile_id','owner','business','mode','module']};packet['topic']=d.get('topic','共用资料');packet['files']=[]
 if not isinstance(d.get('files'),list) or not 1<=len(d['files'])<=12:raise ValueError('请明确列出本次要接回的1至12个成果文件')
 for relative in d['files']:
  f=folder/relative
  if f.is_symlink() or not f.resolve().is_relative_to(folder) or not f.is_file() or f.stat().st_size>6*1024*1024:raise ValueError('只接入本次结果目录内的成果')
  ext=f.suffix.lower()
  if ext not in ['.html','.json','.md','.txt','.png','.jpg','.jpeg','.pdf','.docx']:raise ValueError('请接入原版HTML或交接文档，不上传程序与安装包')
  raw=f.read_bytes();encoding='text' if ext in ['.html','.json','.md','.txt'] else 'base64'
  packet['files'].append({'name':f.name,'encoding':encoding,'content':raw.decode('utf-8') if encoding=='text' else base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest()})
 state=LocalHTTP.get(BASE+'/local-session',timeout=15)
 if state.status_code==404:state=LocalHTTP.get(BASE+'/state',timeout=15)
 state.raise_for_status();token=state.json()['token']
 response=LocalHTTP.post(BASE+'/methods/artifacts',json=packet,headers={'x-workbench-token':token},timeout=30)
 if not response.ok:raise ValueError(response.json().get('detail','成果没有接回，原文件仍保留'))
 return response.json()

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);args=parser.parse_args()
 try:print(json.dumps(publish(args.manifest),ensure_ascii=False))
 except (ValueError,KeyError,OSError) as e:raise SystemExit(str(e))
