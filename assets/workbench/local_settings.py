from pathlib import Path
import json
def api_base():
 root=Path(__file__).resolve().parent;config=root/'data/service.json';port=8766
 if config.exists():
  d=json.loads(config.read_text(encoding='utf-8'))
  if Path(d['app_root']).resolve()!=root:raise ValueError('服务记录属于其他安装，请重新启动本包')
  port=d['port']
 if type(port) is not int or not 1024<=port<=65530:raise ValueError('无效本机端口')
 return 'http://127.0.0.1:'+str(port)+'/api'
