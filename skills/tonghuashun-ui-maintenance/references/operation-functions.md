# 高频操作函数

优先加载本技能 `scripts/ui_ops.mjs`，不要每轮重新从历史聊天拼写M.addCode等临时函数。模块只使用调用方传入的当前CUA app对象；不绑定模型、交易日、对话、股票名单或固定元素编号。当前实现适配macOS同花顺5.3.4及本技能的CUA接口。

## 日常入口

| 函数 | 用途 |
|---|---|
| `observe()` | 读取当前层级和按钮摘要，不修改界面 |
| `openSettings()` | 从已确认主窗口的正确页面进入设置，已在本控制器打开的设置则复用 |
| `selectGroup(name)` | 按精确名称选组 |
| `ensureGroup(name)` | 本地完整查重，已有复用，缺少时新建；不截短名称 |
| `openAdd(group)` / `searchStock(group,security)` | 进入目标组添加页，精确核对代码、名称、市场及add/remove状态 |
| `addStocks(group,securities)` | 同组批量加入，已存在不点击remove |
| `removeStocks(group,securities)` | 优先使用右侧删除股票；目标不在当前可见行时用添加页精确search remove，不分页扫组 |
| `finishAdd()` | 从添加页返回设置 |
| `saveBatch({verifyTargets,exactGroups})` | 一次外层保存，可合并有效目标保留和连板完整集合期望，返回待本地确认的期望 |
| `applyGroup(group,securities,options)` | 同组加入、返回、保存的短批次组合；`createIfMissing=true`仅在上游授权新组时使用 |
| `moveGroup(name,'top'/'bottom')` | 用左侧箭头移动分组，禁止移动系统自选股 |
| `reorderGroups(fullOrder)` | 全组目标逆序置顶，保留系统自选股第一；不计算题材或涨停数 |
| `confirmSaved(receipt,afterSnapshot)` | 接受local_groups.py成功回执后开放下一批，更新本地基线 |
| `useSnapshot(snapshot)` | 无未完成变动时更新当前本地快照 |
| `closeReadOnly()` / `checkpoint()` | 退出本控制器拥有的只读设置，或保存轻量断点 |

不提供清空股票、删除整个分组、恢复自选股、交易账户等快捷函数。这些低频/高影响操作仍按主手册及明确任务范围单独处理。

## 初始化与复用

1. 先按local-files.md生成当前本地快照。只在实际UI修改或具体缺口时附着同花顺一次，读取当次工具文档。
2. 动态导入模块，创建一个控制器，同一批一直复用。未确认来源的既有Unknown弹窗只能observe，不强行取消或接管；已由本控制器从主窗口打开的弹窗直接复用。

```javascript
var fs = await import('node:fs/promises');
var uiModule = await import('file:///ABS_SKILL_DIR/scripts/ui_ops.mjs');
var localBefore = JSON.parse(await fs.readFile(beforePath,'utf8'));
var ops = uiModule.createController(thsApp, {
  snapshot: localBefore,
  onEvent: async event => fs.appendFile(eventPath, JSON.stringify(event)+'\n')
});
await ops.openSettings();
```

`beforePath`、`eventPath`由本轮运行目录提供，均为绝对路径。事件以JSONL追加，不清空已有历史；不要将整个控制器、界面树或元素编号存盘。

个股输入为`{code:'六位字符串',name:'准确名称',market:'SH'/'SZ'/'BJ'}`；也接受沪市/深市/京市/北交所或本地市场值17/33/151。市场必须由行情源或代码表提供，不将所有非6开头代码判为深市，不在名称核对时删除ST标记。

同一工具回合内用少量股票或同一组构成短批次，避免超长调用。模块内部每次动作后取得新状态，按新编号继续；不会因延迟盲目再点一次add/remove图标。模型只输出返回摘要，不逐步重写同一操作。

本轮实际修改前用最新本地快照重算差集；后续直接复用每次成功回执的快照。只在有新的外部改动迹象或异常恢复时再次读取，不每个函数调用前重复snapshot。不同对话重新连接时只恢复本轮文件和checkpoint，重新取得当前app与主窗口状态，不复用旧句柄。

## 保存与本地确认衔接

```javascript
var batch = await ops.applyGroup(groupName, securities);
await fs.writeFile(expectPath, JSON.stringify(batch.expectation,null,2));
nodeRepl.write({results:batch.results, awaitingLocalConfirmation:batch.awaitingLocalConfirmation});
```

随后通过独立终端调用本技能 `local_groups.py verify --before BEFORE --expect EXPECT --output RECEIPT`。不在CUA模块内再实现一份本地文件解析器，也不重开设置逐码盘点。

```javascript
var receipt = JSON.parse(await fs.readFile(receiptPath,'utf8'));
var after = JSON.parse(await fs.readFile(receipt.snapshot_path,'utf8'));
nodeRepl.write(ops.confirmSaved(receipt,after));
```

`saveBatch`只表示UI外层保存已完成；取得成功本地回执之前，不允许下一批修改。新增未保存确认时不允许移除源股。移动/双分类按上游计划先处理全部有效目标，再保存确认，再移除错误源组；移除后的期望仍须包含全部有效目标存在。排序使用上游基于本地成员计算的完整顺序，保存后以本地order回执确认。

`saveBatch`的两个可选参数只追加本地确认期望，不点击对应目标，不重新搜索：

```javascript
// 已确认所有有效目标后，移除错误源组；同一回执确认目标仍在。
await ops.removeStocks(wrongSource, securities);
var batch = await ops.saveBatch({
  verifyTargets: validTargets.map(t => ({group:t.group,code:t.code,present:true}))
});
// 连板最后一个实际修改批次再加入完整目标集合；可为空，但上游须已核实。
// saveBatch({verifyTargets: ladderTargets, exactGroups:{'连板': finalLadderCodes}})
```

`verifyTargets`每项为`{group,code,present}`，`exactGroups`为`{精确组名:[去重六位代码]}`。完整集合须和当前本地基线加本批差集相符；其数量及集合由同一次local_groups.py verify确认。未发生连板变化时直接本地比对，不为exactGroups启动UI。新增分多批时，只在最后一批加入全部目标期望，避免尚未加入的后续代码阻挡前一批保存。

若既无改动也无待核目标，saveBatch返回awaitingLocalConfirmation=false，不调用verify。若已有待核目标但没有任何实际改变，模块不点击外层保存，只返回`no_changes_needed=true`，由本地文件确认目标；上游已能从本地认定全程无变化时，不必为调用模块而启动UI。

本地成员未知的组（当前系统“自选股”即可能如此）不直接调用增删函数；模块会在修改前停止，交给主手册的目标组局部读取/确认路径。正常普通组不受影响。若保存后确实走了局部UI确认，保留该UI回执与控制器断点，不伪造local_file成功回执；受影响组先搁置，独立项可用刷新后的本地数据和新控制器继续。

## 异常和断点

- 单个动作结果尚未出现时只补当前观察，不重复切入口、不盲点第二次；原生响应丢失后先看已落地状态。
- 未决个股动作保存在checkpoint的pendingActions；恢复当前状态后只解决该码，保存前不得把未决动作当成功。
- 控件格式变化、精确证券不唯一或窗口来源不明时停止该项，保留现场与断点；不改窗口布局，不重启客户端。
- checkpoint是任务路由信息，不能用它恢复旧句柄、旧AX编号或未经验证的窗口身份。重新连接仍先识别当前主窗口。

仓库默认测试使用隔离模拟app和合成本地文件，不操作真实分组。真实AX解析测试是可选的本地测试，仓库不包含真实界面夹具，也不以模拟通过声称实际写入成功。真实增删仍以本轮客户端保存文件确认结果。
