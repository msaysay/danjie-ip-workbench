/** How publish accounts look when the uploader environment is missing. */

export function accountFacingStatus(status, publisherReady = true) {
  if (publisherReady === false && status === '已验证') return '登录记录还在，发布器没装好';
  return {已验证: '已登录', 未验证: '还没登录', 需重新验证: '需要重新登录'}[status] || status || '还没登录';
}

export function publisherBlock(publisherReady = true) {
  if (publisherReady !== false) return null;
  return {
    id: 'publisher',
    text: '发布器还没装好。在运行包根目录执行 python scripts/install_optional.py publish 后再扫码。坏掉的 .venv 会被重建。不会登录，也不会发布。',
  };
}
