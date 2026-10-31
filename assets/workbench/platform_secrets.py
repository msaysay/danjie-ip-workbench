"""macOS-only adapter. Encryption keys remain in this user's system Keychain."""
from pathlib import Path
import hashlib,threading
_lock=threading.Lock()
def protect_mac(raw,decode=False):
 try:
  from keyring.backends.macOS import Keyring
  from cryptography.fernet import Fernet
  service='danjie-workbench-'+hashlib.sha256(str(Path(__file__).resolve().parent).encode()).hexdigest()[:20]
  with _lock:
   store=Keyring();key=store.get_password(service,'local-data-encryption-v1')
   if key is None:
    if decode:raise ValueError('本次安装的钥匙串记录不可用，请重新连接自己的TikHub账号')
    key=Fernet.generate_key().decode();store.set_password(service,'local-data-encryption-v1',key)
  box=Fernet(key.encode());return box.decrypt(raw) if decode else box.encrypt(raw)
 except ValueError:raise
 except Exception:raise ValueError('Mac钥匙串未能保存或读取本机密钥，请本人处理系统提示后重试；没有改用明文保存') from None
