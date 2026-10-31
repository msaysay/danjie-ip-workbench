"""Whitelist-only learner archive: runtime data never enters the distribution."""
from pathlib import Path
import zipfile,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
ALLOWED_ROOT={'SKILL.md','00-学员先看这里.md','发给WorkBuddy.txt','启动-Windows.cmd','启动-Mac.command','脱敏与验证说明.json'}
EXCLUDED={'data','.runtime','.venv','__pycache__','node_modules','tests','frozen-skills-v041','runtime-fixes','reference','cookies','browser-profile','.git'}
def files():
 for file in ROOT.rglob('*'):
  if not file.is_file() or file.is_symlink():continue
  rel=file.relative_to(ROOT)
  if any(p in EXCLUDED for p in rel.parts) or file.suffix in ['.pyc','.log','.pid','.db','.sqlite','.sqlite3','.dpapi','.env']:continue
  if rel.parts[0] in ['assets','references'] or (rel.parts[0]=='scripts' and file.name in ['launch.py','student_profile.py','install_optional.py']) or str(rel) in ALLOWED_ROOT:yield file,rel
def main():
 for label in ['windows-x64','mac-arm64','mac-x64']:
  if not (ROOT/'assets/runtimes'/(label+'.tar.gz')).is_file():raise ValueError('先运行fetch_release_assets.py准备依赖')
 if not (ROOT/'assets/workbench/dist/index.html').is_file():raise ValueError('先构建前端')
 if not list((ROOT/'assets/wheels').glob('*.whl')):raise ValueError('核心离线依赖未准备')
 folder=ROOT/'artifacts';folder.mkdir(exist_ok=True);archive=folder/'danjie-workbench-student.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for file,rel in files():
   info=zipfile.ZipInfo.from_file(file,'蛋解工作台/'+rel.as_posix());info.create_system=3;info.external_attr=(0o100755 if file.suffix in ['.sh','.command'] else 0o100644)<<16
   z.writestr(info,file.read_bytes(),compress_type=zipfile.ZIP_DEFLATED)
 with zipfile.ZipFile(archive) as z:
  if z.testzip():raise ValueError('ZIP完整性检查失败')
 record={'file':archive.name,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
 (folder/'SHA256.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(record))
if __name__=='__main__':main()
