import test from 'node:test';
import assert from 'node:assert/strict';
import {accountFacingStatus, publisherBlock} from '../src/publishStatus.js';

test('a saved login is not shown as ready when the publisher is missing', () => {
  assert.equal(accountFacingStatus('已验证', true), '已登录');
  assert.equal(accountFacingStatus('已验证', false), '登录记录还在，发布器没装好');
  assert.equal(accountFacingStatus('未验证', false), '还没登录');
  assert.equal(publisherBlock(true), null);
  const blocked = publisherBlock(false);
  assert.equal(blocked.id, 'publisher');
  assert.match(blocked.text, /install_optional\.py publish/);
  assert.match(blocked.text, /不会发布/);
});
