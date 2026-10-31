"""Offline native Skill previews: only frozen, byte-matching runtime scripts execute."""
from html.parser import HTMLParser
from pathlib import Path
from functools import lru_cache
import ast,base64,hashlib,html,json,re,secrets

SCRIPT=re.compile(r'<script\b([^>]*)>([\s\S]*?)</script\s*>',re.I)
LITERAL=re.compile(r'(?:\b(?:const|let|var)\s+|,)\s*(?:D|m|model|MODEL|DATA|data)\s*=\s*')
def canonical(text):return text.replace('\r\n','\n').replace('\r','\n').strip()
def sha(text):return hashlib.sha256(canonical(text).encode()).hexdigest()

@lru_cache(maxsize=3)
def runtime_sources(root):
 """Only installed frozen renderer sources, never a student's upload, define code."""
 base=Path(root)/'frozen-skills-v041';result=[]
 for p in base.glob('*/**/assets/*.html'):
  result.extend(body for attrs,body in SCRIPT.findall(p.read_text(encoding='utf-8')) if 'application/json' not in attrs.lower())
 for p in base.glob('*/**/assets/*.js'):result.append(p.read_text(encoding='utf-8'))
 # Some original modules author their HTML inside a Python renderer. Extract
 # literal scripts without importing or executing that renderer.
 for p in base.glob('*/**/scripts/render.py'):
  tree=ast.parse(p.read_text(encoding='utf-8'));values={}
  def literal(node):
   if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
   if isinstance(node,ast.Name) and node.id in values:return values[node.id]
   if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):return literal(node.left)+literal(node.right)
   if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='replace' and len(node.args)==2 and not node.keywords:return literal(node.func.value).replace(*[literal(a) for a in node.args])
   raise ValueError('not a static string')
  for node in tree.body:
   if isinstance(node,ast.Assign):
    try:
     value=literal(node.value)
     for target in node.targets:
      if isinstance(target,ast.Name):values[target.id]=value
    except (ValueError,TypeError):pass
  for node in ast.walk(tree):
   if isinstance(node,ast.Constant) and isinstance(node.value,str):
    result.extend(body for attrs,body in SCRIPT.findall(node.value) if 'application/json' not in attrs.lower())
  for value in values.values():result.extend(body for attrs,body in SCRIPT.findall(value) if 'application/json' not in attrs.lower())
 return tuple(result)

@lru_cache(maxsize=3)
def trusted_scripts(root):
 return {sha(body) for body in runtime_sources(root) if body.strip()}

@lru_cache(maxsize=3)
def runtime_templates(root):
 result=[]
 for body in runtime_sources(root):
   if not re.search(r'__(ROOT|MODEL|MODEL_JSON|DATA|PROMPTS)__',body):continue
   chunks=re.split(r'(__(?:ROOT|MODEL|MODEL_JSON|DATA|PROMPTS)__)',canonical(body));pattern='';groups=[]
   for chunk in chunks:
    if re.fullmatch(r'__(ROOT|MODEL|MODEL_JSON|DATA|PROMPTS)__',chunk):
     key=chunk.strip('_')
     if key in groups:pattern+='(?P='+key+')'
     else:pattern+='(?P<'+key+'>'+('[A-Za-z0-9_-]{1,100}' if key=='ROOT' else '[\\s\\S]+?')+')';groups.append(key)
    else:pattern+=re.escape(chunk)
   result.append((re.compile(pattern),groups))
 return result

def trusted_runtime(body,root):
 if sha(body) in trusted_scripts(str(root)):return True
 if len(body)>2_000_000:return False
 for pattern,groups in runtime_templates(str(root)):
  match=pattern.fullmatch(canonical(body))
  if not match:continue
  try:
   for key in groups:
    if key!='ROOT':json.loads(match[key])
   return True
  except ValueError:pass
 return False

def scripts_in(text):return SCRIPT.findall(text)

def declared_modes(text):
 result=[]
 for attrs,body in scripts_in(text):
  try:
   if 'application/json' in attrs.lower():value=json.loads(body)
   else:
    literal=LITERAL.search(body)
    if not literal:continue
    value,_=json.JSONDecoder().raw_decode(body[literal.end():])
   if isinstance(value,dict) and value.get('mode') in ['real','fictional_demo']:result.append(value['mode'])
  except ValueError:pass
 return result

def candidates(text,module=''):
 found={}
 def walk(x,parent=''):
  if isinstance(x,list):
   for value in x:walk(value,parent)
  elif isinstance(x,dict):
   for key in ['question','topic','candidate_title']:
    value=x.get(key)
    if isinstance(value,str) and 5<=len(value.strip())<=400 and (key!='question' or value.rstrip().endswith(('？','?'))):
     title=value.strip();found.setdefault(title,{'id':hashlib.sha256(title.encode()).hexdigest()[:16],'title':title})
   if parent=='topics' and isinstance(x.get('title'),str) and 5<=len(x['title'])<=400:found.setdefault(x['title'],{'id':hashlib.sha256(x['title'].encode()).hexdigest()[:16],'title':x['title']})
   if parent=='topics' and isinstance(x.get('label'),str) and x['label'].endswith(('？','?')) and 5<=len(x['label'])<=400:found.setdefault(x['label'],{'id':hashlib.sha256(x['label'].encode()).hexdigest()[:16],'title':x['label']})
   for key,value in x.items():walk(value,key)
 try:walk(json.loads(text.lstrip('\ufeff')))
 except (ValueError,TypeError):
  for attrs,body in scripts_in(text):
   if 'application/json' in attrs.lower():
    try:walk(json.loads(body))
    except ValueError:pass
   else:
    literal=LITERAL.search(body)
    if literal:
     try:value,_=json.JSONDecoder().raw_decode(body[literal.end():]);walk(value)
     except ValueError:pass
 if not found and module in ['乾坤大挪移','一题多讲']:
  for line in text.splitlines():
   match=re.match(r'^(?:[ABC][^：:]{0,12}|钱|时间|效果|风险|体验|关系)[：:]\s*(.+[？?])\s*$',line.strip())
   if match and 5<=len(match[1])<=400:found[match[1]]={'id':hashlib.sha256(match[1].encode()).hexdigest()[:16],'title':match[1]}
 return list(found.values())[:250]

def topic_binding(text,module,declared='共用资料'):
 # A selected hook, proof or ending has one original question. An entire
 # ten-topic board remains shared. Never infer an identity card's scope as a
 # new topic or replace an explicitly assigned learner label.
 if declared!='共用资料' or module not in ['当头一棒','以理服人','指条明路','开场八式']:return declared
 pool=candidates(text,module)
 return pool[0]['title'] if len(pool)==1 and pool[0]['title'].endswith(('？','?')) else declared

def source_strings(text):
 """Literal output text only: no JS evaluation and no uploaded instructions."""
 values=[]
 def walk(value):
  if isinstance(value,str):values.append(value)
  elif isinstance(value,dict):
   for child in value.values():walk(child)
  elif isinstance(value,list):
   for child in value:walk(child)
 try:walk(json.loads(text.lstrip('\ufeff')))
 except ValueError:
  for attrs,body in scripts_in(text):
   try:
    if 'application/json' in attrs.lower():walk(json.loads(body))
    else:
     for match in LITERAL.finditer(body):
      try:value,_=json.JSONDecoder().raw_decode(body[match.end():]);walk(value)
      except ValueError:pass
   except ValueError:pass
 return values

def preview(text,root,asset_id,module):
 allowed=trusted_scripts(str(root));nonce=secrets.token_hex(16);approved=0;blocked=0
 def replace(match):
  nonlocal approved,blocked
  attrs,body=match.groups()
  if 'application/json' in attrs.lower():
   try:
    data=json.dumps(json.loads(body),ensure_ascii=False).replace('<','\\u003c');ident=re.search(r'\bid=[\"\x27]([A-Za-z0-9_-]+)',attrs)
    data_key=re.search(r'\bdata-k=[\"\x27]([A-Za-z0-9_-]+)',attrs)
    return '<script type="application/json"'+(' id="'+ident[1]+'"' if ident else '')+(' data-k="'+data_key[1]+'"' if data_key else '')+'>'+data+'</script>'
   except ValueError:return ''
  if trusted_runtime(body,root):approved+=1;return '<script nonce="'+nonce+'">'+body+'</script>'
  blocked+=1;return ''
 body=SCRIPT.sub(replace,text)
 # The original interview renderer links its installed stylesheet. Resolve
 # that exact local asset only; uploaded paths and remote URLs stay blocked.
 if module=='六脉神剑':
  assets=next((Path(root)/'frozen-skills-v041/11').glob('*/assets'))
  texture='data:image/png;base64,'+base64.b64encode((assets/'texture.png').read_bytes()).decode()
  css=(assets/'style.css').read_text(encoding='utf-8').replace('texture.png',texture)
  body=re.sub(r'<link\s+rel="stylesheet"\s+href="style.css"\s*/?>',lambda _:'<style>'+css+'</style>',body)
 body=re.sub(r'<meta\b(?=[^>]*http-equiv\s*=\s*["\x27]?refresh)[^>]*>','',body,flags=re.I)
 # No same-origin permission, network, popups, forms or unknown inline event handlers.
 csp="default-src 'none'; script-src 'nonce-"+nonce+"'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'"
 bridge=Path(__file__).with_name('method_bridge.js').read_text(encoding='utf-8').replace('ASSET_ID',json.dumps(asset_id)).replace('MODULE',json.dumps(module)).replace('CANDIDATES',json.dumps([x['title'] for x in candidates(text)],ensure_ascii=False).replace('<','\\u003c'))
 return {'html':'<meta http-equiv="Content-Security-Policy" content="'+html.escape(csp,quote=True)+'">'+body+'<script nonce="'+nonce+'">'+bridge+'</script>','interactive':approved>0,'approved_scripts':approved,'blocked_scripts':blocked}
