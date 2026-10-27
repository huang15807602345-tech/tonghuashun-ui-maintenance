import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {createController,parseAX,normalizeSecurity} from './ui_ops.mjs';

const securities={
  '600001':{code:'600001',name:'沪市样本',market:'SH'},
  '000001':{code:'000001',name:'深市样本',market:'SZ'},
  '920001':{code:'920001',name:'北交所样本',market:'BJ'},
};
const copy=x=>JSON.parse(JSON.stringify(x));

class FakeApp {
  constructor(scene='main') {
    this.scene=scene;this.order=['自选股','观察','连板','核心','机器人','医药'];
    this.groups={'自选股':[],'观察':[],'连板':[],'核心':[],'机器人':[],'医药':['600001']};
    this.group='机器人';this.selectedStock=null;this.query='';this.newName='';
    this.serial=0;this.events=[];this.lag=0;this.lagReads=0;this.shown=null;this.throwAfterToggle=false;
  }
  snapshot(){return {source:'local_file',status:'complete',directory_complete:true,captured_at:new Date().toISOString(),
    order:[...this.order],groups:Object.fromEntries(this.order.map(name=>[name,{name,complete:name!=='自选股',
      members:name==='自选股'?null:this.groups[name].map(code=>({code,market:{SH:'17',SZ:'33',BJ:'151'}[securities[code]?.market]??'33'})),
      total:name==='自选股'?null:this.groups[name].length}]))};}
  async getAXState(){
    this.map=new Map();let index=++this.serial*1000;const lines=['Window: "fixture", App: 同花顺.'];
    const add=(depth,body,action)=>{const id=index++;lines.push('\t'.repeat(depth)+id+' '+body);if(action)this.map.set(id,action);return id;};
    if(this.scene==='main') {add(0,'标准窗口 ID: 主窗口');add(1,'按钮 分组设置',{type:'openSettings'});}
    else if(this.scene==='settings') {
      add(0,'表单');add(1,'container');add(2,'滚动区');add(3,'表格');
      for(const name of this.order){add(4,'row'+(name===this.group?' (selected)':''));add(5,'单元格');add(6,'文本 '+name,{type:'selectGroup',name});}
      add(2,'按钮 +, Help: 添加分组',{type:'openNew'});add(2,'按钮 −, Help: 删除分组',{type:'forbiddenGroupDelete'});
      add(2,'按钮 ⬆︎, Help: 置顶',{type:'groupTop'});add(2,'按钮 ⬇︎, Help: 置底',{type:'groupBottom'});
      add(1,'按钮 确定',{type:'save'});add(1,'text 自选分组设置（共'+this.order.length+'组）： 所选分组成分股设置');
      add(1,'container');add(2,'滚动区');add(3,'表格');
      const members=this.hideStocks?[]:this.groups[this.group];
      for(const code of members){add(4,'row'+(this.selectedStock===code?' (selected)':''));add(5,'单元格');add(6,'text '+code+' '+securities[code].name,{type:'selectStock',code});}
      add(2,'按钮 +, Help: 添加股票',{type:'openAdd'});add(2,'按钮 −, Help: 删除股票',{type:'deleteStock'});
      add(2,'按钮 ⬆︎, Help: 置顶',{type:'forbiddenStockTop'});add(2,'按钮 ⬇︎, Help: 置底',{type:'forbiddenStockBottom'});
      add(2,'按钮 清空股票',{type:'forbiddenClear'});add(2,'按钮 恢复自选股',{type:'forbiddenRestore'});
      add(1,'按钮 取消',{type:'cancel'});
    } else if(this.scene==='newGroup') {
      add(0,'表单');add(1,'文本 请输入分组名称，如：长线价值股');
      add(1,'文本栏 (settable) '+(this.newName?'Value: '+this.newName+', Placeholder: 分组名称':'分组名称'),{type:'groupField'});
      add(1,'按钮 确定',{type:'createConfirm'});add(1,'text '+this.newName.length+'/20');add(1,'按钮 取消',{type:'newCancel'});add(1,'文本 新建分组');
    } else if(this.scene==='addStocks') {
      add(0,'表单');add(1,'文本 添加股票');
      add(1,'文本栏 (settable) '+(this.query?'Value: '+this.query+', Placeholder: ':'')+'输入代码／名称／选股条件／图片',{type:'searchField'});
      const security=securities[this.query];
      if(security) {
        const actual=this.groups[this.group].includes(this.query);
        if(this.lag>0){this.lag--;if(this.lag===0)this.shown=actual;}else this.shown=actual;
        const market=this.wrongMarket?'沪市':{SH:'沪市',SZ:'深市',BJ:'北交所'}[security.market];
        const name=this.wrongName?'不同证券':security.name;
        const result=()=>{add(1,'container');add(2,'text '+security.code+' '+name+' '+market);add(2,'图像 search '+(this.shown?'remove':'add'),{type:'toggle',code:this.query});};
        result();if(this.duplicateResult)result();
      }
      add(1,'按钮 完成',{type:'finishAdd'});
    } else {add(0,'表单');add(1,'文本 unrelated dialog');}
    return lines.join('\n');
  }
  async click(index){
    const action=this.map.get(index);assert.ok(action,'never click an index from an older observation');
    this.events.push(action);if(action.type.startsWith('forbidden'))throw Error('wrong control scope');
    switch(action.type){
      case'openSettings':this.scene='settings';break;
      case'selectGroup':this.group=action.name;break;
      case'openAdd':this.scene='addStocks';this.query='';break;
      case'finishAdd':this.scene='settings';break;
      case'openNew':this.scene='newGroup';this.newName='';break;
      case'createConfirm':this.groups[this.newName]=[];this.order.push(this.newName);this.group=this.newName;this.scene='settings';break;
      case'save':this.scene='main';break;
      case'cancel':this.scene='main';break;
      case'selectStock':this.selectedStock=action.code;break;
      case'deleteStock':this.groups[this.group]=this.groups[this.group].filter(c=>c!==this.selectedStock);break;
      case'groupTop':this.order=this.order.filter(n=>n!==this.group);this.order.splice(1,0,this.group);break;
      case'groupBottom':this.order=this.order.filter(n=>n!==this.group);this.order.push(this.group);break;
      case'toggle':{
        const group=this.groups[this.group],present=group.includes(action.code);this.shown=present;
        if(present)this.groups[this.group]=group.filter(c=>c!==action.code);else group.push(action.code);
        this.lag=this.lagReads;
        if(this.throwAfterToggle){this.throwAfterToggle=false;throw Error('native response lost after landed click');}
        break;
      }
    }
  }
  async setValue(index,value){
    const action=this.map.get(index);assert.ok(action,'fresh index required for input');
    if(action.type==='searchField'){this.query=value;this.shown=null;this.lag=0;}
    else if(action.type==='groupField')this.newName=value;
    else throw Error('input was not a text field');
  }
}

function fixture(){const app=new FakeApp();return {app,ops:createController(app,{snapshot:app.snapshot()})};}
function receiptFor(expectation,before,after){
  const set=(snap,g)=>new Set(snap.groups[g]?.members?.map(m=>m.code)??[]);
  const targets=expectation.targets.map(t=>({...t,pass:set(after,t.group).has(t.code)===t.present}));
  const groups=[...new Set([...expectation.changes.map(c=>c.group),...Object.keys(expectation.exact_groups??{})])].map(group=>{
    const expected=expectation.exact_groups?.[group]?new Set(expectation.exact_groups[group]):set(before,group);
    for(const c of expectation.changes.filter(c=>c.group===group))(c.action==='add'?expected.add.bind(expected):expected.delete.bind(expected))(c.code);
    const actual=set(after,group);
    return {group,pass:JSON.stringify([...expected].sort())===JSON.stringify([...actual].sort()),expected_count:expected.size,actual_count:actual.size};
  });
  const created_groups=expectation.created_groups.map(group=>({group,pass:!!after.groups[group]}));
  const checks={targets,groups,created_groups};
  if(expectation.order)checks.order={actual:after.order,pass:JSON.stringify(expectation.order)===JSON.stringify(after.order)};
  return {schema_version:'ths-local-verification-1',source:'local_file',verification_method:'local_file_after_save',
    pass:[...targets,...groups,...created_groups,checks.order??{pass:true}].every(p=>p.pass),
    settings_saved:expectation.settings_saved,saved_at:expectation.saved_at,verified_at:new Date().toISOString(),checks};
}

test('real observed settings: left and right controls are distinguished', {skip:!process.env.THS_UI_AX_FIXTURE},()=>{
  const view=parseAX(fs.readFileSync(process.env.THS_UI_AX_FIXTURE,'utf8'));
  assert.equal(view.layer,'settings');assert.equal(view.groupCount,view.groups.length);
  assert.notEqual(view.controls.addGroup.index,view.controls.addStock.index);
  assert.notEqual(view.controls.groupTop.index,view.controls.stockTop.index);
});
test('main-to-settings provenance and current selection',async()=>{
  const {ops}=fixture();await ops.openSettings();const result=await ops.selectGroup('医药');assert.equal(result.mainVerified,true);
});
test('pre-existing unknown-owner dialog is inspected but never mutated',async()=>{
  const app=new FakeApp('settings'),ops=createController(app,{snapshot:app.snapshot()});
  assert.equal((await ops.observe()).layer,'settings');await assert.rejects(()=>ops.openAdd('机器人'),/verified main-window/);assert.equal(app.events.length,0);
});
test('existing group is reused without opening UI',async()=>{
  const {app,ops}=fixture();assert.equal((await ops.ensureGroup('机器人')).status,'already_exists');assert.equal(app.events.length,0);
});
test('new group uses exact literal name and leaves outer save pending',async()=>{
  const {app,ops}=fixture();await ops.ensureGroup('新组[甲]+');assert.ok(app.groups['新组[甲]+']);assert.equal(ops.checkpoint().dirty,true);
  assert.equal(app.events.filter(e=>e.type==='save').length,0);
});
test('overlength group name is rejected before UI actions',async()=>{
  const {app,ops}=fixture();await assert.rejects(()=>ops.ensureGroup('长'.repeat(21)),/20-character/);assert.equal(app.events.length,0);
});
test('explicit Shanghai Shenzhen and Beijing markets all work',async()=>{
  const {app,ops}=fixture();const results=await ops.addStocks('机器人',Object.values(securities));
  assert.equal(results.length,3);assert.equal(app.groups['机器人'].length,3);
  assert.throws(()=>normalizeSecurity({code:'920001',name:'北交所样本'}),/Explicit/);
});
test('already-present stock is not toggled off',async()=>{
  const {app,ops}=fixture();app.groups['机器人'].push('000001');
  assert.equal((await ops.addStocks('机器人',[securities['000001']]))[0].status,'already_present');
  assert.equal(app.events.filter(e=>e.type==='toggle').length,0);
});
test('delayed add status causes one click, never a second remove click',async()=>{
  const {app,ops}=fixture();app.lagReads=2;await ops.addStocks('机器人',[securities['000001']]);
  assert.equal(app.events.filter(e=>e.type==='toggle').length,1);assert.ok(app.groups['机器人'].includes('000001'));
});
test('lost response after a landed click is recovered without replay',async()=>{
  const {app,ops}=fixture();app.throwAfterToggle=true;await ops.addStocks('机器人',[securities['000001']]);
  assert.equal(app.events.filter(e=>e.type==='toggle').length,1);
});
test('unresolved add stays pending and later resolves from state without toggling again',async()=>{
  const {app,ops}=fixture();app.lagReads=10;await assert.rejects(()=>ops.addStocks('机器人',[securities['000001']]),/pending/);
  assert.equal(ops.checkpoint().pendingActions.length,1);await assert.rejects(()=>ops.saveBatch(),/pending stock/);
  app.lag=0;const result=await ops.addStocks('机器人',[securities['000001']]);assert.equal(result[0].recovered,true);
  assert.equal(app.events.filter(e=>e.type==='toggle').length,1);
});
for(const problem of ['wrongMarket','wrongName','duplicateResult'])test(`${problem} is rejected before stock mutation`,async()=>{
  const {app,ops}=fixture();app[problem]=true;await assert.rejects(()=>ops.addStocks('机器人',[securities['920001']]));
  assert.equal(app.events.filter(e=>e.type==='toggle').length,0);
});
test('group batch saves once, then requires exact local confirmation',async()=>{
  const {app,ops}=fixture(),before=app.snapshot();const result=await ops.applyGroup('机器人',Object.values(securities));
  assert.equal(app.events.filter(e=>e.type==='save').length,1);assert.equal(result.awaitingLocalConfirmation,true);
  await assert.rejects(()=>ops.selectGroup('医药'),/Confirm the saved batch/);
  const receipt=receiptFor(result.expectation,before,app.snapshot());
  assert.equal(ops.confirmSaved(receipt,app.snapshot()).confirmed,true);await ops.openSettings();
});
test('failed or incomplete local confirmation cannot release the next mutation',async()=>{
  const {app,ops}=fixture();const result=await ops.applyGroup('机器人',[securities['000001']]);
  const receipt=receiptFor(result.expectation,new FakeApp().snapshot(),app.snapshot());
  assert.throws(()=>ops.confirmSaved({...receipt,pass:false},app.snapshot()),/successful local/);
  receipt.checks.targets=[];assert.throws(()=>ops.confirmSaved(receipt,app.snapshot()),/does not confirm/);
});
test('additions must be saved and locally confirmed before source removal',async()=>{
  const {app,ops}=fixture(),before=app.snapshot();await ops.addStocks('机器人',[securities['600001']]);
  await assert.rejects(()=>ops.removeStocks('医药',[securities['600001']]),/confirm all additions/);
  const saved=await ops.saveBatch();ops.confirmSaved(receiptFor(saved.expectation,before,app.snapshot()),app.snapshot());
  await ops.removeStocks('医药',[securities['600001']]);assert.deepEqual(app.groups['医药'],[]);
});
test('receipt must confirm the expected changed-group count',async()=>{
  const {app,ops}=fixture(),before=app.snapshot();const saved=await ops.applyGroup('机器人',[securities['000001']]);
  const receipt=receiptFor(saved.expectation,before,app.snapshot());receipt.checks.groups[0].actual_count=999;
  assert.throws(()=>ops.confirmSaved(receipt,app.snapshot()),/count\/delta/);
});
test('visible stock removal uses right delete-stock button only',async()=>{
  const {app,ops}=fixture();await ops.removeStocks('医药',[securities['600001']]);assert.deepEqual(app.groups['医药'],[]);
  assert.ok(app.events.some(e=>e.type==='deleteStock'));assert.ok(!app.events.some(e=>e.type==='forbiddenGroupDelete'));
});
test('offscreen stock removal uses exact search without paging all members',async()=>{
  const {app,ops}=fixture();app.hideStocks=true;await ops.removeStocks('医药',[securities['600001']]);assert.deepEqual(app.groups['医药'],[]);
  assert.equal(app.events.filter(e=>e.type==='toggle').length,1);
});
test('absent stock removal makes no toggle and no group change',async()=>{
  const {app,ops}=fixture();assert.equal((await ops.removeStocks('机器人',[securities['000001']]))[0].status,'already_absent');
  assert.equal(app.events.filter(e=>e.type==='toggle').length,0);
});
test('group arrows never touch stock arrows and system group is fixed',async()=>{
  const {app,ops}=fixture();await ops.moveGroup('医药','top');assert.equal(app.order[1],'医药');await ops.moveGroup('医药','bottom');
  assert.equal(app.order.at(-1),'医药');await assert.rejects(()=>ops.moveGroup('自选股','top'),/cannot be moved/);
  assert.ok(!app.events.some(e=>e.type.startsWith('forbidden')));
});
test('full group reorder uses inverse top moves, then one local order confirmation',async()=>{
  const {app,ops}=fixture(),before=app.snapshot(),desired=['自选股','观察','连板','核心','医药','机器人'];
  await ops.reorderGroups(desired);assert.deepEqual(app.order,desired);const result=await ops.saveBatch();
  assert.equal(ops.confirmSaved(receiptFor(result.expectation,before,app.snapshot()),app.snapshot()).confirmed,true);
});
test('no-change batch skips save; owned read-only settings can close',async()=>{
  const {app,ops}=fixture();const before=app.snapshot();const result=await ops.applyGroup('医药',[securities['600001']]);
  assert.equal(result.expectation.settings_saved,false);assert.equal(app.events.filter(e=>e.type==='save').length,0);
  ops.confirmSaved(receiptFor(result.expectation,before,app.snapshot()),app.snapshot());await ops.closeReadOnly();assert.equal(app.scene,'main');
});
test('event sink appends; checkpoint does not contain live indices or AX',async()=>{
  const app=new FakeApp(),events=[{kind:'previous'}],ops=createController(app,{snapshot:app.snapshot(),onEvent:async e=>events.push(e)});
  await ops.openSettings();assert.equal(events[0].kind,'previous');const state=ops.checkpoint();assert.ok(!('ax'in state));assert.ok(!('index'in state));
  assert.equal(typeof ops.clearStocks,'undefined');assert.equal(typeof ops.deleteGroup,'undefined');
});
test('empty add/remove lists do not even observe or open UI',async()=>{
  const {app,ops}=fixture();assert.deepEqual(await ops.addStocks('机器人',[]),[]);
  assert.deepEqual(await ops.removeStocks('机器人',[]),[]);assert.equal(app.serial,0);assert.equal(app.events.length,0);
});
test('empty save creates no verification trap or unnecessary UI action',async()=>{
  const {app,ops}=fixture();assert.equal((await ops.saveBatch()).awaitingLocalConfirmation,false);assert.equal(app.serial,0);
  await ops.openSettings();assert.equal((await ops.saveBatch()).awaitingLocalConfirmation,false);await ops.closeReadOnly();assert.equal(app.scene,'main');
});
test('unknown local membership is rejected before any UI mutation',async()=>{
  const {app,ops}=fixture();await assert.rejects(()=>ops.addStocks('自选股',[securities['000001']]),/local membership unavailable/);
  assert.equal(app.events.length,0);assert.equal(app.serial,0);
});
test('empty new group needs local member-count zero confirmation',async()=>{
  const {app,ops}=fixture(),before=app.snapshot();await ops.ensureGroup('空新组');const saved=await ops.saveBatch();
  assert.deepEqual(saved.expectation.exact_groups,{'空新组':[]});
  assert.equal(ops.confirmSaved(receiptFor(saved.expectation,before,app.snapshot()),app.snapshot()).confirmed,true);
});
test('UI batch interoperates with the real Python file-verification program offline',async()=>{
  const {app,ops}=fixture(),before=app.snapshot();await ops.ensureGroup('新批次组');await ops.addStocks('新批次组',[securities['920001']]);
  const saved=await ops.saveBatch({verifyTargets:[{group:'医药',code:'600001',present:true}],exactGroups:{'新批次组':['920001']}});
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'ths-ui-integration-'));
  try {
    const source=path.join(temp,'source');fs.mkdirSync(source);
    const builder=String.raw`import sys,json,plistlib,base64
from pathlib import Path
d=json.load(sys.stdin);root=Path(sys.argv[1])
def vi(n):
 b=bytearray()
 while n>=128:b.append((n&127)|128);n>>=7
 b.append(n);return bytes(b)
def field(n,v):return vi(n*8+2)+vi(len(v))+v
def put(k,v):
 o=['$null',{'self.ID':plistlib.UID(2),'self.value':plistlib.UID(3),'self.version':1},k,v]
 p={'$version':100000,'$archiver':'NSKeyedArchiver','$top':{'root':plistlib.UID(1)},'$objects':o}
 (root/('fixture__'+base64.b64encode(k).decode()+'.dat')).write_bytes(plistlib.dumps(p,fmt=plistlib.FMT_BINARY))
ids=[]
for i,name in enumerate(d['order']):
 if name=='自选股':continue
 gid=100+i;ids.append(gid);m=d['groups'][name]['members'];codes=''.join(x['code']+'|' for x in m);markets=''.join(x['market']+'|' for x in m)
 put(b'\x08'+vi(gid),field(1,base64.b64encode(name.encode('gb18030')))+field(2,b'')+field(3,(codes+','+markets).encode()))
put(b'\x08\x00',field(1,','.join(format(x,'x') for x in ids).encode()))
put(b'StockGroupCommon',field(1,json.dumps({'0':'\b"'}).encode()))`;
    const made=spawnSync('python3',['-c',builder,source],{input:JSON.stringify(app.snapshot()),encoding:'utf8'});
    assert.equal(made.status,0,made.stderr);
    const beforePath=path.join(temp,'before.json'),expectPath=path.join(temp,'expected.json'),receiptPath=path.join(temp,'receipt.json');
    fs.writeFileSync(beforePath,JSON.stringify(before));fs.writeFileSync(expectPath,JSON.stringify(saved.expectation));
    const script=new URL('./local_groups.py',import.meta.url).pathname;
    const result=spawnSync('python3',[script,'--source-dir',source,'verify','--before',beforePath,'--expect',expectPath,'--output',receiptPath,'--timeout-seconds','0'],{encoding:'utf8'});
    assert.equal(result.status,0,result.stdout+result.stderr);const receipt=JSON.parse(fs.readFileSync(receiptPath));
    assert.equal(ops.confirmSaved(receipt,JSON.parse(fs.readFileSync(receipt.snapshot_path))).confirmed,true);
  } finally {fs.rmSync(temp,{recursive:true,force:true});}
});

test('source removal receipt must retain all valid target groups without revisiting their UI',async()=>{
  const app=new FakeApp();app.groups['机器人']=['600001'];
  const before=app.snapshot(),ops=createController(app,{snapshot:before});
  await ops.removeStocks('医药',[securities['600001']]);
  const eventCount=app.events.length;
  const saved=await ops.saveBatch({verifyTargets:[{group:'机器人',code:'600001',present:true}],exactGroups:{'医药':[]}});
  assert.deepEqual(app.events.slice(eventCount).map(e=>e.type),['save']);
  const receipt=receiptFor(saved.expectation,before,app.snapshot());
  const missing=copy(receipt);missing.checks.targets=missing.checks.targets.filter(t=>t.group!=='机器人');
  assert.throws(()=>ops.confirmSaved(missing,app.snapshot()),/does not confirm/);
  assert.equal(ops.confirmSaved(receipt,app.snapshot()).confirmed,true);
});

test('ladder final exact set is confirmed in the same save receipt',async()=>{
  const {app,ops}=fixture(),before=app.snapshot();await ops.addStocks('连板',[securities['000001'],securities['920001']]);
  const saved=await ops.saveBatch({exactGroups:{'连板':['000001','920001']}});
  const receipt=receiptFor(saved.expectation,before,app.snapshot());
  const wrong=copy(receipt);wrong.checks.groups[0].actual_count=1;
  assert.throws(()=>ops.confirmSaved(wrong,app.snapshot()),/confirmation missing/);
  assert.equal(ops.confirmSaved(receipt,app.snapshot()).confirmed,true);
});

test('conflicting retained targets and incomplete ladder expectations do not click save',async()=>{
  const {app,ops}=fixture();await ops.addStocks('连板',[securities['000001']]);
  const eventCount=app.events.length;
  await assert.rejects(()=>ops.saveBatch({verifyTargets:[{group:'连板',code:'000001',present:false}]}),/Contradictory/);
  await assert.rejects(()=>ops.saveBatch({exactGroups:{'连板':[]}}),/conflicts/);
  assert.equal(app.events.length,eventCount);
  const before=new FakeApp().snapshot(),saved=await ops.saveBatch({exactGroups:{'连板':['000001']}});
  assert.equal(ops.confirmSaved(receiptFor(saved.expectation,before,app.snapshot()),app.snapshot()).confirmed,true);
});
