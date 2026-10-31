import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {REGISTER_URL,WIZARD_STEPS,OUTSIDE_NOTE,TRY_NOTE} from '../src/tikhubConnect.js';
import {engagement,scanSummary,whyRecommend} from '../src/inspirationView.js';

const src=name=>readFileSync(new URL('../src/'+name,import.meta.url),'utf8');

test('connect wizard keeps the referral link and four spoken steps',()=>{
 assert.equal(REGISTER_URL,'https://user.tikhub.io/register?ref=u58I2I4n');
 assert.deepEqual(WIZARD_STEPS.map(step=>step.title),['连接','注册','配置 Key','完成连接']);
 assert.match(OUTSIDE_NOTE,/官网或文档/);
 assert.match(OUTSIDE_NOTE,/不另收费/);
 assert.match(TRY_NOTE,/不会自动重试/);
 const wizard=src('TikHubConnectWizard.jsx');
 assert.match(wizard,/测一下/);
 assert.match(wizard,/打开 TikHub 注册或登录/);
 assert.match(wizard,/打开控制台复制密钥/);
});

test('inspiration keeps xiaohongshu search and publish screens do not offer it',()=>{
 const radar=src('InspirationRadar.jsx');
 assert.match(radar,/xiaohongshu:'小红书'/);
 assert.match(radar,/为什么推荐/);
 assert.match(radar,/TikHubConnectWizard/);
 assert.match(radar,/radar-scan/);
 const main=src('main.jsx');
 const publishing=src('PublishingPage.jsx');
 const settings=src('SettingsPage.jsx');
 for(const file of [main,publishing,settings]){
  assert.doesNotMatch(file,/小红书/);
  assert.doesNotMatch(file,/xiaohongshu/);
 }
 assert.match(settings,/TikHubConnectWizard/);
});

test('scan summary and recommendation use returned fields only',()=>{
 const feed={
  keyword_items:[
   {id:'a',platform:'douyin',query:'酱酒',kind:'keyword',likes:10,comments:2,shares:0,saves:1,selection_reason:'标题提到酱酒；近7天发布；有公开互动可回看'},
   {id:'b',platform:'xiaohongshu',query:'酱酒',kind:'keyword',likes:1,comments:0,shares:0,saves:0},
   {id:'c',platform:'wechat',query:'团购',kind:'keyword',views:100},
  ],
  account_items:[{id:'d',platform:'douyin',query:'作者甲',kind:'account',likes:9,comments:9,shares:9,saves:9}],
  boards:[{platform:'weibo',items:[{id:'e',platform:'weibo',query:'微博热榜',kind:'hot',heat:20}]}],
 };
 const summary=scanSummary(feed);
 assert.equal(summary.items,5);
 assert.equal(summary.platformCount,4);
 assert.equal(summary.topicCount,4);
 assert.ok(summary.highEngagement>=1);
 assert.match(summary.engagementNote,/不跨平台比播放/);
 assert.equal(engagement(feed.keyword_items[2]),null);
 assert.match(whyRecommend(feed.keyword_items[0]),/酱酒/);
 assert.match(whyRecommend(feed.account_items[0]),/关注的作者/);
 assert.match(whyRecommend(feed.boards[0].items[0]),/热榜/);
});
