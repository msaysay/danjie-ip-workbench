import test from 'node:test';import assert from 'node:assert/strict';import {freshMemory,fileAsset,appendAsset,checkedMemory,verifyMemory,contextText,safeReading} from '../src/memoryContract.js';
const make=()=>freshMemory('test-memory','测试学员（模拟）','测试业务','fictional_demo');

test('native cards and retained versions can exceed the old 24MB limit',async()=>{
 let m=make();const a=await fileAsset(new File(['x'.repeat(4*1024*1024)],'原版.html'),'当头一棒','题0');
 for(let i=0;i<7;i++)m=appendAsset(m,{...a,id:'native-'+i,topic:'题'+i});
 assert.equal(m.assets.length,7);assert.equal(checkedMemory(m).assets.length,7);assert.ok(new TextEncoder().encode(JSON.stringify(m)).length>24*1024*1024);
});
test('duplicates keep one original and revisions preserve both bodies',async()=>{
 let m=make();const a=await fileAsset(new File(['初稿'], '脚本.md'),'完整脚本','报价');m=appendAsset(m,a);assert.equal(appendAsset(m,a).assets.length,1);
 m=appendAsset(m,await fileAsset(new File(['修订稿'],'脚本.md'),'完整脚本','报价'));assert.equal(m.assets.length,2);assert.deepEqual(m.assets.map(a=>a.version),[1,2]);assert.match(contextText(m),/修订稿/);assert.doesNotMatch(contextText(m),/初稿/);
});
test('export/restore verifies every original, keeps BOM bytes and never trusts confirmation flags',async()=>{
 let m=make();m=appendAsset(m,await fileAsset(new File(['\uFEFF中文原稿'],'脚本.txt'),'完整脚本','主线'));m.assets[0].review='confirmed';const restored=await verifyMemory(JSON.stringify(m));assert.equal(restored.assets[0].review,'pending');assert.equal(restored.assets[0].content,'\uFEFF中文原稿');m.assets[0].content='被改写';await assert.rejects(()=>verifyMemory(JSON.stringify(m)),/校验/);
});
test('unknown extension, large file and invalid memory mode do not enter archive',async()=>{
 await assert.rejects(()=>fileAsset(new File(['x'],'运行.exe'),'其他成品','主线'),/支持/);await assert.rejects(()=>fileAsset(new File([new Uint8Array(6*1024*1024+1)],'大文件.txt'),'其他成品','主线'),/6MB/);const m=make();m.mode='unknown';assert.throws(()=>checkedMemory(m),/真实业务/);
});
test('binary records remain explicit about missing extraction; imports do not execute HTML scripts',async()=>{
 let m=make();m=appendAsset(m,await fileAsset(new File([new Uint8Array([1,2,3])],'卡片.png'),'客群卡','共用'));assert.match(contextText(m),/未提取文字/);assert.match(safeReading('<script>fetch("https://x")</script>'),/default-src 'none'/);
});
