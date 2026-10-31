"""Download only locked public runtime archives and pinned Python wheels."""
from pathlib import Path
import hashlib,json,sys,subprocess,urllib.request
ROOT=Path(__file__).resolve().parents[1]
def main():
 manifest=json.loads((ROOT/'assets/runtime-manifest.json').read_text(encoding='utf-8'));folder=ROOT/'assets/runtimes';folder.mkdir(exist_ok=True)
 for row in manifest['runtimes']:
  if not row['url'].startswith('https://github.com/astral-sh/python-build-standalone/releases/download/'):raise ValueError('未登记的运行时来源')
  target=folder/(row['platform']+'.tar.gz')
  if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=row['sha256']:
   temp=target.with_suffix('.download')
   request=urllib.request.Request(row['url'],headers={'User-Agent':'Danjie-Workbench-Release'})
   with urllib.request.urlopen(request,timeout=240) as response,temp.open('wb') as output:
    while block:=response.read(1024*1024):output.write(block)
   if hashlib.sha256(temp.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('下载内容与登记SHA256不符')
   temp.replace(target)
  print('运行时已核对：'+row['platform'],flush=True)
 wheels=ROOT/'assets/wheels';wheels.mkdir(exist_ok=True)
 for platform in ['win_amd64','macosx_11_0_arm64','macosx_13_0_x86_64']:
  subprocess.run([sys.executable,'-m','pip','--isolated','download','--index-url','https://pypi.org/simple','--only-binary=:all:','--platform',platform,'--implementation','cp','--python-version','312','--dest',str(wheels),'-r',str(ROOT/'assets/workbench/requirements-core.lock.txt')],check=True)
if __name__=='__main__':main()
