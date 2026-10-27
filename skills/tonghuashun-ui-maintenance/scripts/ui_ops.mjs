// Reusable Tonghuashun operations. Uses only the supplied, documented CUA app API.
// Never reads accounts, writes client data files, or trusts saved element indices.
export const VERSION = '1.1.0';
const cleanName = value => String(value).normalize('NFKC').replace(/\s/g, '');
const textRoles = new Set(['文本', 'text']);
const childrenOf = node => node.children.flatMap(child => [child, ...childrenOf(child)]);
const only = (items, label) => {
  if (items.length !== 1) throw new Error(`${label}: expected one current control, found ${items.length}`);
  return items[0];
};
const byLabel = (nodes, label) => nodes.filter(n => n.role === '按钮' && n.label === label);
const hasHelp = (node, help) => node.role === '按钮' && node.help === help;

export function normalizeSecurity(input) {
  if (!input || typeof input.code !== 'string' || !/^\d{6}$/.test(input.code))
    throw new Error('A-share security code must be a six-character string');
  if (typeof input.name !== 'string' || !input.name.trim()) throw new Error('Security name is required');
  const markets = {SH:'SH',SZ:'SZ',BJ:'BJ','沪市':'SH','深市':'SZ','京市':'BJ','北交所':'BJ','17':'SH','33':'SZ','151':'BJ'};
  const market = markets[input.market];
  if (!market) throw new Error('Explicit SH/SZ/BJ market is required; do not guess all non-6 codes as Shenzhen');
  return {code:input.code, name:input.name, market};
}

export function parseAX(ax) {
  if (typeof ax !== 'string') throw new Error('Expected current full AX text');
  const nodes = [], stack = [];
  for (const line of ax.split('\n')) {
    if (/^(Selected:|Note:|The focused UI element)/.test(line)) break;
    const match = line.match(/^(\s*)(\d+)\s+(.+)$/);
    if (!match) continue;
    const depth = match[1].replace(/\t/g, '    ').length;
    const body = match[3], role = body.split(' ')[0];
    const afterRole = body.slice(role.length).trim();
    const help = afterRole.match(/(?:^|, )Help: (.*?)(?:, (?:ID|Value|Placeholder):|$)/)?.[1];
    const label = afterRole.replace(/^\([^)]*\)\s*/, '').split(/, (?:Help|ID|Value|Placeholder):| Secondary Actions:/)[0];
    const node = {index:Number(match[2]), depth, body, role, label, help,
      value:afterRole.match(/(?:^|\s|, )Value: (.*?)(?:, Placeholder:|$)/)?.[1],
      selected:/\(selected\)/.test(body), children:[], parent:null};
    while (stack.length && stack.at(-1).depth >= depth) stack.pop();
    if (stack.length) {node.parent = stack.at(-1); node.parent.children.push(node);}
    nodes.push(node); stack.push(node);
  }
  const forms = nodes.filter(n => ['表单','标准窗口','dialog','window'].includes(n.role) && !n.parent);
  const form = forms[0] ?? null;
  const main = nodes.some(n => n.role === '标准窗口' && /(?:^|[, ])ID: 主窗口(?:,|$)/.test(n.body));
  const addGroup = nodes.find(n => hasHelp(n,'添加分组'));
  const addStock = nodes.find(n => hasHelp(n,'添加股票'));
  const left = addGroup?.parent ?? null, right = addStock?.parent ?? null;
  function rows(container) {
    if (!container) return [];
    const table = childrenOf(container).find(n => n.role === '表格');
    return table ? childrenOf(table).filter(n => n.role === 'row').map(row => ({row,
      selected:row.selected || childrenOf(row).some(n => n.selected),
      texts:childrenOf(row).filter(n => textRoles.has(n.role))})) : [];
  }
  const groups = rows(left).map(r => ({name:only(r.texts,'group label').label,
    index:only(r.texts,'group label').index, selected:r.selected}));
  const stocks = rows(right).flatMap(r => r.texts.flatMap(n => {
    const m = n.label.match(/^(\S+)\s+(.+)$/);
    return m ? [{code:m[1],name:m[2],index:n.index,selected:r.selected}] : [];
  }));
  const searchField = nodes.find(n => ['文本栏','text field','textfield'].includes(n.role)
    && /输入代码.*名称.*选股条件.*图片/.test(n.body));
  const groupField = nodes.find(n => n.role === '文本栏' && /分组名称/.test(n.body));
  const rootButtons = form?.children.filter(n => n.role === '按钮') ?? [];
  const scoped = (container,help) => container ? childrenOf(container).find(n=>hasHelp(n,help)) : null;
  const controls = {
    addGroup, addStock,
    deleteGroup:left ? childrenOf(left).find(n=>hasHelp(n,'删除分组')) : null,
    deleteStock:right ? childrenOf(right).find(n=>hasHelp(n,'删除股票')) : null,
    groupTop:scoped(left,'置顶'), groupBottom:scoped(left,'置底'),
    stockTop:scoped(right,'置顶'), stockBottom:scoped(right,'置底'),
    save:byLabel(rootButtons,'确定')[0], cancel:byLabel(rootButtons,'取消')[0],
    finish:byLabel(nodes,'完成')[0],
    settings:byLabel(nodes,'分组设置')[0], searchField, groupField,
  };
  const results = [];
  for (const node of nodes.filter(n => textRoles.has(n.role))) {
    const match = node.label.match(/^(\d{6})\s+(.+)\s+(沪市|深市|京市|北交所)$/);
    if (!match) continue;
    for (let parent=node.parent; parent; parent=parent.parent) {
      const descendants=childrenOf(parent);
      const icons=descendants.filter(n=>n.role==='图像' && /^search (add|remove)$/.test(n.label));
      const securities=descendants.filter(n=>textRoles.has(n.role) && /^\d{6}\s+.+\s+(沪市|深市|京市|北交所)$/.test(n.label));
      if (icons.length===1 && securities.length===1) {
        results.push({code:match[1],name:match[2],market:normalizeSecurity({code:match[1],name:match[2],market:match[3]}).market,
          status:icons[0].label.split(' ')[1],index:icons[0].index}); break;
      }
    }
  }
  const layer = addGroup && addStock ? 'settings' : searchField && controls.finish ? 'addStocks'
    : groupField && /新建分组|请输入分组名称/.test(ax) ? 'newGroup' : main ? 'main' : 'unknown';
  return {ax,nodes,main,layer,groups,stocks,results,controls,
    selectedGroup:groups.find(g=>g.selected)?.name ?? null,
    groupCount:Number(ax.match(/自选分组设置（共(\d+)组）/)?.[1]) || null};
}

export function createController(app, {snapshot, onEvent} = {}) {
  if (!app || typeof app.getAXState!=='function') throw new Error('A documented CUA app binding is required');
  if (!snapshot || snapshot.source!=='local_file' || snapshot.directory_complete!==true)
    throw new Error('Load a current local_groups.py snapshot before UI operations');
  const state={view:null,mainVerified:false,activeGroup:null,dirty:false,created:new Set(),
    changes:new Map(),targets:new Map(),exactGroups:new Map(),intents:new Map(),order:null,pending:null,events:[],snapshot};
  const key=(group,code)=>JSON.stringify([group,code]);
  async function event(kind,details={}) {
    const item={kind,...details,at:new Date().toISOString()};state.events.push(item);
    if (onEvent) await onEvent(item);return item;
  }
  function summary() {return {version:VERSION,layer:state.view?.layer??'unobserved',mainVerified:state.mainVerified,
    activeGroup:state.activeGroup,dirty:state.dirty,awaitingLocalConfirmation:!!state.pending,
    createdGroups:[...state.created],changeCount:state.changes.size,eventCount:state.events.length};}
  async function refresh() {
    state.view=parseAX(await app.getAXState({emit:false,disableDiffing:true}));
    if (state.view.main) state.mainVerified=true;
    if (state.view.layer==='unknown') state.mainVerified=false;
    return state.view;
  }
  function writable() {if(state.pending) throw new Error('Confirm the saved batch from local files before another mutation');}
  function memberScope(group) {
    if(!state.created.has(group)&&state.snapshot.groups[group]?.complete!==true)
      throw new Error(`Current local membership unavailable for ${group}; use the skill's targeted recovery before any mutation`);
  }
  function owned(layer) {
    if(!state.mainVerified || state.view?.layer!==layer)
      throw new Error(`Need verified main-window ${layer}; leave an unverified pre-existing dialog unchanged`);
  }
  async function waitFor(predicate,label) {
    // Read again only while the requested result is missing; never repeat a toggle click.
    for(let attempt=0;attempt<2;attempt++) {
      if(predicate(state.view))return state.view;
      await refresh();
    }
    if(!predicate(state.view))throw new Error(`UI result pending: ${label}`);
    return state.view;
  }
  async function click(node,predicate,label) {
    if(!node)throw new Error(`Current control unavailable: ${label}`);
    let error;
    try {await app.click(node.index);}catch(e){error=e;}
    await refresh();
    try {return await waitFor(predicate,label);}catch(e){if(error)e.cause=error;throw e;}
  }
  async function openSettingsInternal() {
    if(state.view.layer==='settings'){owned('settings');return;}
    if(state.view.layer==='addStocks'){await finishAddInternal();return;}
    owned('main');
    await click(state.view.controls.settings,v=>v.layer==='settings','open group settings');
    await event('settings_opened');
  }
  async function finishAddInternal() {
    owned('addStocks');
    await click(state.view.controls.finish,v=>v.layer==='settings','finish stock search');
    state.activeGroup=null;
  }
  async function selectInternal(name) {
    await openSettingsInternal();owned('settings');
    const group=only(state.view.groups.filter(g=>g.name===name),`group ${name}`);
    if(!group.selected)await click(group,v=>v.layer==='settings'&&v.selectedGroup===name,`select ${name}`);
    return name;
  }
  async function openAddInternal(name) {
    if(state.view.layer==='addStocks'&&state.activeGroup===name){owned('addStocks');return;}
    await selectInternal(name);
    await click(state.view.controls.addStock,v=>v.layer==='addStocks',`open stock search for ${name}`);
    state.activeGroup=name;
  }
  function resultFor(security) {
    const hit=only(state.view.results.filter(h=>h.code===security.code),'exact security result');
    if(cleanName(hit.name)!==cleanName(security.name)||hit.market!==security.market)
      throw new Error(`Security name/market mismatch for ${security.code}`);
    return hit;
  }
  async function searchInternal(group,security) {
    await openAddInternal(group);owned('addStocks');
    if(state.activeGroup!==group)throw new Error('Stock-search group context changed');
    let field=state.view.controls.searchField;
    if(field.value!==security.code) {
      await app.setValue(field.index,security.code);await refresh();
    }
    await waitFor(v=>v.layer==='addStocks'&&v.controls.searchField?.value===security.code
      &&v.results.filter(h=>h.code===security.code).length===1,`search ${security.code}`);
    return resultFor(security);
  }
  function target(group,code,present) {state.targets.set(key(group,code),{group,code,present});}
  function changed(group,code,action) {
    const id=key(group,code),previous=state.changes.get(id);
    if(previous&&previous.action!==action)state.changes.delete(id);
    else state.changes.set(id,{group,code,action});
  }
  async function ensureStockInternal(group,security,present) {
    const hit=await searchInternal(group,security),desired=present?'remove':'add';
    target(group,security.code,present);
    const id=key(group,security.code),action=present?'add':'remove';
    if(hit.status===desired) {
      if(state.intents.get(id)?.action===action) {
        changed(group,security.code,action);state.intents.delete(id);
        await event('stock_outcome_recovered',{group,...security,action,immediateVerified:true,persistedVerified:false});
        return {group,code:security.code,status:present?'added':'removed',recovered:true,persistedVerified:false};
      }
      return {group,code:security.code,status:present?'already_present':'already_absent'};
    }
    state.dirty=true;
    state.intents.set(id,{group,code:security.code,action});
    await click(hit,v=>v.layer==='addStocks'&&v.results.some(h=>h.code===security.code&&h.status===desired),
      `${present?'add':'remove'} ${security.code}`);
    resultFor(security);
    changed(group,security.code,action);state.intents.delete(id);
    await event(present?'stock_added':'stock_removed',{group,...security,immediateVerified:true,persistedVerified:false});
    return {group,code:security.code,status:present?'added':'removed',persistedVerified:false};
  }
  async function saveInternal() {
    if(state.intents.size)throw new Error('Resolve pending stock outcomes before saving this batch');
    if(state.view.layer==='addStocks')await finishAddInternal();
    owned('settings');
    const expectation={settings_saved:false,no_changes_needed:!state.dirty,
      changes:[...state.changes.values()],targets:[...state.targets.values()],created_groups:[...state.created]};
    if(state.created.size||state.exactGroups.size)expectation.exact_groups={...Object.fromEntries([...state.created].map(group=>{
      const codes=new Set();for(const c of expectation.changes.filter(c=>c.group===group))
        (c.action==='add'?codes.add.bind(codes):codes.delete.bind(codes))(c.code);
      return [group,[...codes]];
    })),...Object.fromEntries(state.exactGroups)};
    if(state.order)expectation.order=state.order;
    if(state.dirty) {
      await click(state.view.controls.save,v=>v.layer==='main','save group settings');
      expectation.settings_saved=true;expectation.saved_at=new Date().toISOString();
      await event('settings_saved',{savedAt:expectation.saved_at});
    }
    state.pending={expectation};
    return {expectation,awaitingLocalConfirmation:true};
  }
  async function moveGroupInternal(name,direction) {
    if(name==='自选股')throw new Error('System self group cannot be moved');
    await selectInternal(name);owned('settings');
    const before=state.view.groups.map(g=>g.name);
    if(state.view.groupCount!==before.length)throw new Error('Current group controls are incomplete; do not guess positions');
    const targetIndex=direction==='top'?1:before.length-1;
    if(before[targetIndex]===name)return {group:name,status:'already_positioned'};
    const expected=before.filter(g=>g!==name);expected.splice(targetIndex,0,name);
    state.dirty=true;
    await click(state.view.controls[direction==='top'?'groupTop':'groupBottom'],
      v=>v.layer==='settings'&&JSON.stringify(v.groups.map(g=>g.name))===JSON.stringify(expected),`move group ${name}`);
    state.order=expected;await event('group_moved',{group:name,direction});
    return {group:name,status:'moved',persistedVerified:false};
  }
  const api={
    useSnapshot(next){
      writable();if(state.dirty||state.intents.size)throw new Error('Do not replace the before snapshot of an unfinished batch');
      if(next?.source!=='local_file'||next.directory_complete!==true)throw new Error('A current local-file snapshot is required');
      state.snapshot=next;return summary();
    },
    async observe(){await refresh();return {...summary(),buttons:Object.fromEntries(Object.entries(state.view.controls)
      .filter(([,n])=>n).map(([k,n])=>[k,{label:n.label,help:n.help??null}]))};},
    async openSettings(){writable();await refresh();await openSettingsInternal();return summary();},
    async selectGroup(name){writable();await refresh();await selectInternal(name);return summary();},
    async openAdd(group){writable();await refresh();await openAddInternal(group);return summary();},
    async searchStock(group,input){writable();await refresh();const hit=await searchInternal(group,normalizeSecurity(input));
      return {group,code:hit.code,name:hit.name,market:hit.market,status:hit.status};},
    async addStocks(group,inputs){writable();const securities=inputs.map(normalizeSecurity);if(!securities.length)return [];memberScope(group);await refresh();
      const results=[];for(const security of securities)results.push(await ensureStockInternal(group,security,true));return results;},
    async removeStocks(group,inputs){writable();const securities=inputs.map(normalizeSecurity);if(!securities.length)return [];memberScope(group);await refresh();
      if(state.created.size||[...state.changes.values(),...state.intents.values()].some(c=>c.action==='add'))
        throw new Error('Save and locally confirm all additions before removing source stocks');
      await openSettingsInternal();await selectInternal(group);
      const results=[];
      for(const security of securities) {
        if(state.view.layer!=='settings')await finishAddInternal();
        await selectInternal(group);
        const visible=state.view.stocks.filter(s=>s.code===security.code);
        if(visible.length===1) {
          const stock=visible[0];
          if(cleanName(stock.name)!==cleanName(security.name))throw new Error('Visible security name mismatch');
          if(!stock.selected)await click(stock,v=>v.layer==='settings'&&v.selectedGroup===group&&v.stocks.some(s=>s.code===security.code&&s.selected),'select stock to remove');
          state.dirty=true;
          state.intents.set(key(group,security.code),{group,code:security.code,action:'remove'});
          await click(state.view.controls.deleteStock,v=>v.layer==='settings'&&v.selectedGroup===group&&!v.stocks.some(s=>s.code===security.code),'remove selected stock');
          changed(group,security.code,'remove');state.intents.delete(key(group,security.code));target(group,security.code,false);
          await event('stock_removed',{group,...security,immediateVerified:true,persistedVerified:false});
          results.push({group,code:security.code,status:'removed',persistedVerified:false});
        } else results.push(await ensureStockInternal(group,security,false));
      }
      return results;
    },
    async finishAdd(){writable();await refresh();await finishAddInternal();return summary();},
    async ensureGroup(name){
      writable();if(typeof name!=='string'||!name.trim()||name!==name.trim()||[...name].length>20)
        throw new Error('Use an exact nonempty group name within the UI 20-character limit');
      if(state.snapshot.order.includes(name)||state.created.has(name))return {group:name,status:'already_exists'};
      await refresh();await openSettingsInternal();
      if(state.view.groups.some(g=>g.name===name))throw new Error('Group appeared after local snapshot; refresh local data before mutation');
      await click(state.view.controls.addGroup,v=>v.layer==='newGroup','open new group dialog');
      await app.setValue(state.view.controls.groupField.index,name);await refresh();
      if(state.view.controls.groupField?.value!==name)throw new Error('Group name was not set exactly');
      state.dirty=true;
      await click(state.view.controls.save,v=>v.layer==='settings'&&v.groups.some(g=>g.name===name&&g.selected),'create group');
      state.created.add(name);await event('group_created',{group:name,persistedVerified:false});
      return {group:name,status:'created',persistedVerified:false};
    },
    async moveGroup(name,direction='top'){
      writable();if(!['top','bottom'].includes(direction))throw new Error('Direction must be top or bottom');
      await refresh();return moveGroupInternal(name,direction);
    },
    async reorderGroups(order){
      writable();await refresh();await openSettingsInternal();
      const actual=state.view.groups.map(g=>g.name);
      if(!Array.isArray(order)||order[0]!=='自选股'||new Set(order).size!==order.length
        ||order.length!==actual.length||order.some(n=>!actual.includes(n)))throw new Error('Order must include every exact group once, with system self first');
      const results=[];
      if(JSON.stringify(actual)!==JSON.stringify(order))
        for(const name of order.slice(1).reverse())results.push(await moveGroupInternal(name,'top'));
      state.order=[...order];return {moves:results.length,awaitingSave:state.dirty};
    },
    async saveBatch({verifyTargets=[],exactGroups={}}={}){
      writable();
      if(!Array.isArray(verifyTargets)||!exactGroups||Array.isArray(exactGroups)||typeof exactGroups!=='object')
        throw new Error('Use verifyTargets array and exactGroups object');
      const plannedTargets=new Map(state.targets);
      for(const t of verifyTargets){
        if(!t||typeof t.group!=='string'||typeof t.code!=='string'||!/^\d{6}$/.test(t.code)||typeof t.present!=='boolean')
          throw new Error('Verification targets require exact group, six-digit code and boolean present');
        memberScope(t.group);
        const id=key(t.group,t.code),existing=plannedTargets.get(id);
        if(existing&&existing.present!==t.present)throw new Error('Contradictory verification targets');
        plannedTargets.set(id,{group:t.group,code:t.code,present:t.present});
      }
      for(const [group,codes] of Object.entries(exactGroups)){
        memberScope(group);
        if(!Array.isArray(codes)||codes.some(code=>typeof code!=='string'||!/^\d{6}$/.test(code))||new Set(codes).size!==codes.length)
          throw new Error('Exact group membership requires unique six-digit codes');
        const expected=new Set(state.snapshot.groups[group]?.members?.map(m=>m.code)??[]);
        for(const c of state.changes.values())if(c.group===group)(c.action==='add'?expected.add.bind(expected):expected.delete.bind(expected))(c.code);
        if(expected.size!==codes.length||codes.some(code=>!expected.has(code)))
          throw new Error('Exact group target conflicts with the current batch delta');
      }
      state.targets=plannedTargets;
      for(const [group,codes] of Object.entries(exactGroups))state.exactGroups.set(group,[...codes]);
      if(!state.dirty&&!state.targets.size&&!state.created.size&&!state.exactGroups.size&&!state.order&&!state.intents.size)
        return {expectation:{settings_saved:false,no_changes_needed:true,changes:[],targets:[],created_groups:[]},awaitingLocalConfirmation:false};
      await refresh();return saveInternal();
    },
    async applyGroup(group,inputs,{createIfMissing=false}={}){
      writable();const securities=inputs.map(normalizeSecurity);
      if(!securities.length)throw new Error('No stock mutations requested; verify unchanged targets locally without opening UI');
      if(createIfMissing)await api.ensureGroup(group);
      memberScope(group);
      await refresh();const results=[];
      for(const security of securities)results.push(await ensureStockInternal(group,security,true));
      await finishAddInternal();return {results,...await saveInternal()};
    },
    confirmSaved(receipt,afterSnapshot){
      if(!state.pending)throw new Error('No saved batch is awaiting confirmation');
      const expectation=state.pending.expectation;
      if(receipt?.schema_version!=='ths-local-verification-1'||receipt.pass!==true||receipt.source!=='local_file')
        throw new Error('A successful local_groups.py receipt is required');
      if(expectation.settings_saved&&(receipt.saved_at!==expectation.saved_at||receipt.settings_saved!==true))
        throw new Error('Receipt does not belong to this completed save');
      for(const t of expectation.targets)
        if(!receipt.checks?.targets?.some(p=>p.group===t.group&&p.code===t.code&&p.present===t.present&&p.pass===true))
          throw new Error(`Receipt does not confirm ${t.group}/${t.code}`);
      for(const group of new Set(expectation.changes.map(c=>c.group)))
      {
        const expected=new Set(state.snapshot.groups[group]?.members?.map(m=>m.code)??[]);
        for(const change of expectation.changes.filter(c=>c.group===group))
          (change.action==='add'?expected.add.bind(expected):expected.delete.bind(expected))(change.code);
        if(!receipt.checks?.groups?.some(p=>p.group===group&&p.pass===true&&p.expected_count===expected.size&&p.actual_count===expected.size))
          throw new Error('Changed group count/delta confirmation missing');
      }
      for(const group of expectation.created_groups)
        if(!receipt.checks?.created_groups?.some(p=>p.group===group&&p.pass===true)
          ||!receipt.checks?.groups?.some(p=>p.group===group&&p.pass===true&&p.actual_count===expectation.exact_groups[group].length))
          throw new Error('Created group confirmation missing');
      for(const [group,codes] of Object.entries(expectation.exact_groups??{}))
        if(!receipt.checks?.groups?.some(p=>p.group===group&&p.pass===true&&p.expected_count===codes.length&&p.actual_count===codes.length))
          throw new Error('Exact group membership confirmation missing');
      if(expectation.order&&(!receipt.checks?.order?.pass||JSON.stringify(receipt.checks.order.actual)!==JSON.stringify(expectation.order)))
        throw new Error('Final order confirmation missing');
      if(afterSnapshot?.source!=='local_file'||afterSnapshot.directory_complete!==true)throw new Error('Load the receipt snapshot to continue');
      state.snapshot=afterSnapshot;state.pending=null;state.dirty=false;state.created.clear();state.changes.clear();state.targets.clear();state.exactGroups.clear();state.order=null;
      return {confirmed:true,method:receipt.verification_method,...summary()};
    },
    async closeReadOnly(){
      writable();if(state.dirty)throw new Error('Do not cancel a batch containing unconfirmed changes');
      await refresh();if(state.view.layer==='addStocks')await finishAddInternal();
      if(state.view.layer==='main')return summary();owned('settings');
      await click(state.view.controls.cancel,v=>v.layer==='main','close owned read-only settings');return summary();
    },
    checkpoint(){return {...summary(),pendingVerification:state.pending?JSON.parse(JSON.stringify(state.pending.expectation)):null,
      targets:[...state.targets.values()],exactGroups:Object.fromEntries(state.exactGroups),changes:[...state.changes.values()],pendingActions:[...state.intents.values()]};},
  };
  return api;
}
