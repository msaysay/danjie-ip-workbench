"""Local source development without importing any existing installation data."""
from pathlib import Path
import argparse,os,sys,json,zipfile,subprocess
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'assets/workbench'
def prepare():
 with zipfile.ZipFile(ROOT/'assets/frameworks.zip') as archive:
  for entry in archive.infolist():
   if not (APP/entry.filename).resolve().is_relative_to(APP.resolve()):raise ValueError('框架路径超出工作目录')
  for prefix in ['frozen-skills-v041','runtime-fixes','reference']:
   target=APP/prefix
   if target.exists():continue
   archive.extractall(APP,members=[e for e in archive.infolist() if e.filename.startswith(prefix+'/')])
 if len(list((APP/'frozen-skills-v041').glob('*/**/SKILL.md')))!=12:raise ValueError('原版框架未齐备')
 print('12项框架已在当前源码副本展开。')
 note_publisher_venv()
def note_publisher_venv():
 venv=APP/'vendor'/'social-auto-upload'/'.venv'
 python=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
 if venv.exists() and not python.is_file():
  print('发布器环境不完整：social-auto-upload/.venv 在，但没有 Python。prepare 不联网安装。请执行 python scripts/install_optional.py publish，它会删掉坏环境再重建，不会登录或发布。', flush=True)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','test','serve']);parser.add_argument('--port',type=int,default=8766);a=parser.parse_args()
 prepare()
 if a.action=='test':
  raise SystemExit(subprocess.call([sys.executable,'-X','utf8','-m','unittest','discover','-s','tests'],cwd=APP))
 if a.action=='serve':
  if not 1024<=a.port<=65530:raise ValueError('端口无效')
  os.environ['WORKBENCH_PORT']=str(a.port);os.environ['WORKBENCH_ANALYTICS_PORT']=str(a.port+4)
  os.environ['PYTHONUTF8']='1';sys.path.insert(0,str(APP));os.chdir(APP)
  import server,uvicorn
  (APP/'data/service.json').write_text(json.dumps({'port':a.port,'app_root':str(APP.resolve())}),encoding='utf-8')
  uvicorn.run(server.app,host='127.0.0.1',port=a.port)
if __name__=='__main__':main()
