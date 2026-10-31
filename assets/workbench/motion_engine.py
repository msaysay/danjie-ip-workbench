"""Pinned MotionGit public package runner; no downloaded commands or user shell text."""
from __future__ import annotations
import hashlib,json,os,pathlib,shutil,sys,zipfile
import requests

PACKAGE_SHA='472a95af35f8e0c09c0f7dc2ca0992b7c9a3405c5aa8063730c347fc4e015c21'
PACKAGE_URL='https://raw.githubusercontent.com/motiontemplates/385712/9dfbe7d7c6a6d4aa03f6f8e2f2285e631099faae/downloads/kinetic-tech-zh.motion'

def install(data:pathlib.Path,node:str,run):
    cache=data/'template-packages';cache.mkdir(exist_ok=True)
    archive=cache/'kinetic-tech-0.2.7-zh.motion';runner=cache/'kinetic-tech-0.2.7-zh'
    if not archive.exists():
        temporary=archive.with_suffix('.part')
        with requests.get(PACKAGE_URL,stream=True,timeout=60) as response:
            response.raise_for_status();size=0
            with temporary.open('wb') as f:
                for chunk in response.iter_content(1024*1024):
                    size+=len(chunk)
                    if size>100*1024*1024:raise RuntimeError('模板包超过预期大小')
                    f.write(chunk)
        if hashlib.file_digest(temporary.open('rb'),'sha256').hexdigest()!=PACKAGE_SHA:raise RuntimeError('模板包 SHA256 与锁定版本不符，未执行')
        temporary.replace(archive)
    if hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()!=PACKAGE_SHA:raise RuntimeError('本地模板包校验失败')
    if not runner.exists():
        staging=cache/'kinetic-tech-unpacking'
        if staging.exists():raise RuntimeError('存在未完成的解包目录，请先检查，未覆盖')
        staging.mkdir()
        with zipfile.ZipFile(archive) as z:
            if sum(i.file_size for i in z.infolist())>512*1024*1024:raise RuntimeError('模板展开过大')
            for i in z.infolist():
                path=(staging/i.filename).resolve()
                if not path.is_relative_to(staging.resolve()) or (i.external_attr>>16)&0o170000==0o120000:raise RuntimeError('不安全的模板路径')
            z.extractall(staging)
        if 'MIT License' not in (staging/'licenses/TEMPLATE-LICENSE.txt').read_text(encoding='utf-8'):raise RuntimeError('模板许可与预期不符')
        staging.replace(runner)
    if not (runner/'node_modules/playwright-core/package.json').exists():
        npm_cli=pathlib.Path(node).parent/'node_modules/npm/bin/npm-cli.js'
        if not npm_cli.exists():raise RuntimeError('未找到 Node 随附的 npm CLI')
        run([node,npm_cli,'ci','--ignore-scripts'],cwd=runner,timeout=600)
    python=runner/'.venv'/'Scripts'/'python.exe'
    if not python.exists():run([sys.executable,'-m','venv','--system-site-packages',runner/'.venv'],timeout=120)
    ready=runner/'runtime-ready.json'
    if not ready.exists():
        run([python,'-m','pip','install','soundfile==0.13.1','pyloudnorm==0.1.1','jsonschema'],timeout=600)
        ready.write_text(json.dumps({'archive_sha256':PACKAGE_SHA,'installed':True}),encoding='utf-8')
    return runner,python

def render(data:pathlib.Path,node:str,run,folder:pathlib.Path,title:str,keyword:str,explanation:str):
    runner,python=install(data,node,run)
    folder.mkdir(parents=True,exist_ok=False)
    user={'mode':'user-media','language':'zh','layout':'landscape','duration':8,'title':title[:45],'presenterLabel':'',
        'scenes':[{'id':'B1','title':'本期主题'}],'content':{},'basic':{'keyword':keyword,'explanation':explanation},
        'media':{'presenter':{'mode':'none'},'voice':{'mode':'none'},'music':{'mode':'none'}},'soundEffects':'native','captions':[]}
    source=folder/'user.json';source.write_text(json.dumps(user,ensure_ascii=False,indent=2),encoding='utf-8')
    commands=[('plan',['plan','--input',source,'--out',folder/'plan.json']),('prepare',['prepare','--input',source,'--out',folder/'instance']),
              ('preview',['preview','--instance',folder/'instance','--out',folder/'preview.png','--time','2']),
              ('render',['render','--instance',folder/'instance','--out',folder/'native.mp4'])]
    for stage,args in commands:
        result=run([python,runner/'adapter.py',*args],cwd=runner,timeout=1200)
        (folder/(stage+'.log')).write_text(result,encoding='utf-8')
    final=folder/'native-with-audio.mp4'
    if not final.exists():raise RuntimeError('模板入口未生成含原生音效的成片')
    run(['ffmpeg','-v','error','-i',final,'-f','null','-'],timeout=300)
    probe=json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',final]))
    return {'file':str(final.relative_to(data)).replace('\\','/'),'preview':str((folder/'preview.png').relative_to(data)).replace('\\','/'),
            'duration':float(probe['format']['duration']),'sha256':hashlib.file_digest(final.open('rb'),'sha256').hexdigest(),
            'package_sha256':PACKAGE_SHA,'template':'385712','template_version':'0.2.7-open-beta','native_fps':60,'width':1920,'height':1080,
            'source_project':str(folder),'decoded':True,'position':'intro','audio':'native template effects; no voice or music added'}
