from pathlib import Path
import argparse,os,sys,subprocess,json,shutil
PKG=Path(__file__).resolve().parents[1];APP=PKG/'assets/workbench'
def run(args,**kwargs):subprocess.run([str(x) for x in args],check=True,cwd=APP,**kwargs)
def py(folder):return folder/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
def main():
 p=argparse.ArgumentParser();p.add_argument('feature',choices=['publish','analytics','transcribe']);a=p.parse_args()
 print('此扩展需要联网下载开源依赖；不会登录账号或发布。',flush=True)
 env={**os.environ,'PYTHONUTF8':'1','PLAYWRIGHT_BROWSERS_PATH':str(APP/'data/browsers')}
 if a.feature=='transcribe':
  run([sys.executable,'-I','-m','pip','--isolated','install','--index-url','https://pypi.org/simple','faster-whisper>=1.1,<2'],env=env)
  run([sys.executable,'-c',"from huggingface_hub import snapshot_download;snapshot_download('Systran/faster-whisper-small')"],env=env)
 else:
  repo=APP/'vendor'/('social-auto-upload' if a.feature=='publish' else 'douyin-mcp');venv=repo/'.venv'
  if not py(venv).exists():run([sys.executable,'-m','venv',venv],env=env)
  run([py(venv),'-m','pip','--isolated','install','--index-url','https://pypi.org/simple','-e',repo],env=env)
  if a.feature=='publish':
   if not (repo/'conf.py').exists():shutil.copyfile(repo/'conf.example.py',repo/'conf.py')
   for name in ['cookies','logs','media','videos','db']:(repo/name).mkdir(exist_ok=True)
  run([py(venv),'-m','patchright' if a.feature=='publish' else 'playwright','install','chromium'],env=env)
 print('扩展安装完成。请由学员本人登录自己的账号。')
if __name__=='__main__':main()
