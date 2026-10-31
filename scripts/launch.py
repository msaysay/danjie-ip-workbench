"""Run the package in its own portable Python; no global installs or sample data."""
from pathlib import Path
import argparse,sys,os,json,subprocess,time,urllib.request,webbrowser,zipfile,hashlib
PKG=Path(__file__).resolve().parents[1];APP=PKG/'assets/workbench'
def run(args):subprocess.run([str(x) for x in args],check=True,cwd=APP)
def get(url):
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open(url,timeout=2) as response:return json.load(response)
def install():
 stamp=PKG/'.runtime/core-installed.json';lock=APP/'requirements-core.lock.txt';sha=hashlib.sha256(lock.read_bytes()).hexdigest()
 if not stamp.exists() or json.loads(stamp.read_text(encoding='utf-8')).get('requirements_sha256')!=sha:
  print('正在安装本包自带依赖，不修改系统Python。',flush=True)
  with (PKG/'.runtime/install.log').open('w',encoding='utf-8') as log:
   subprocess.run([sys.executable,'-I','-X','utf8','-m','pip','--isolated','install','--no-index','--disable-pip-version-check','--no-warn-script-location','--find-links',str(PKG/'assets/wheels'),'-r',str(lock)],cwd=APP,stdout=log,stderr=subprocess.STDOUT,check=True)
  stamp.write_text(json.dumps({'requirements_sha256':sha}),encoding='utf-8')
 if not (APP/'frozen-skills-v041').is_dir():
  with zipfile.ZipFile(PKG/'assets/frameworks.zip') as archive:
   for item in archive.infolist():
    path=(APP/item.filename).resolve()
    if not path.is_relative_to(APP.resolve()):raise RuntimeError('框架文件路径校验失败')
   archive.extractall(APP)
def check():
 sys.path.insert(0,str(APP));import fastapi,uvicorn,requests,feedparser,multipart
 from PIL import Image
 assert len(list((APP/'frozen-skills-v041').glob('*/**/SKILL.md')))==12
 assert (APP/'dist/index.html').exists()
 print(json.dumps({'core_ready':True,'methods':12,'python':sys.version.split()[0],'data_dir':str(APP/'data')},ensure_ascii=False))
def start(port,show):
 data=APP/'data';data.mkdir(exist_ok=True);address='http://127.0.0.1:'+str(port)
 try:
  health=get(address+'/api/health')
 except Exception:health=None
 if health:
  if Path(health['data_dir']).resolve()!=data.resolve():raise RuntimeError('此端口属于另一份工作台。请保留它，用 --port 指定其他端口。')
 else:
  # Never inherit the instructor's model or API settings when a new copy starts.
  # Learners configure their own connections in this installation.
  env={k:v for k,v in os.environ.items() if not k.startswith('WORKBENCH_MODEL_')}
  env.update(PYTHONUTF8='1',PYTHONNOUSERSITE='1',WORKBENCH_PORT=str(port),WORKBENCH_ANALYTICS_PORT=str(port+4))
  for name,script in [('server','server.py'),('analytics','analytics_bridge.py')]:
   kwargs={'cwd':APP,'env':env,'stdin':subprocess.DEVNULL,'stdout':(data/(name+'.out.log')).open('ab'),'stderr':(data/(name+'.err.log')).open('ab')}
   if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS
   else:kwargs['start_new_session']=True
   proc=subprocess.Popen([sys.executable,'-X','utf8',str(APP/script)],**kwargs)
   (data/(name+'.pid')).write_text(str(proc.pid),encoding='ascii')
  for _ in range(60):
   try:
    health=get(address+'/api/health')
    if Path(health['data_dir']).resolve()==data.resolve():break
   except Exception:time.sleep(.5)
  else:raise RuntimeError('启动未完成，请让WorkBuddy读取本目录data/server.err.log排查。')
 (data/'service.json').write_text(json.dumps({'port':port,'app_root':str(APP.resolve())}),encoding='utf-8')
 print('工作台已打开：'+address,flush=True)
 if show:webbrowser.open(address)
def main():
 p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');p.add_argument('--no-browser',action='store_true');p.add_argument('--no-register',action='store_true');p.add_argument('--port',type=int,default=8766);a=p.parse_args()
 if not 1024<=a.port<=65530:raise RuntimeError('端口范围无效')
 install();check()
 if not a.check_only:
  start(a.port,not a.no_browser)
  if not a.no_register:
   file=Path.home()/'.danjie-workbench/locations.json';file.parent.mkdir(exist_ok=True)
   old=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {'locations':[]}
   old['locations']=[x for x in old.get('locations',[]) if x.get('path')!=str(PKG)]+[{'path':str(PKG),'port':a.port}]
   file.write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':
 try:main()
 except Exception as e:print('启动未完成：'+str(e),file=sys.stderr);sys.exit(1)
