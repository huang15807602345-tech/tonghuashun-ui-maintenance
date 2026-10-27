# 同花顺本地文件读取与保存确认

日常维护的分组目录、成员和排序均优先读客户端本地文件；不依赖共享历史档案、旧日组名白名单或UI全量盘点。实际新增、移除和排序仍通过Computer Use完成，禁止直接改同花顺数据文件。

## 来源与范围

本技能的 `scripts/local_groups.py` 自动发现当前Mac的 `~/Library/Containers/cn.com.10jqka.macstock/Data/Documents/cloud_store/blockstock_*/public`。多来源时不按最新时间猜账号，不读取凭据；记录来源歧义，继续独立研究。

当前5.3.4格式中，数值分组文件为Apple归档包裹的长度编码字段：字段1为Base64/GB18030组名，字段2非空为条件选股公式，字段3为代码列表与市场列表。数值ID 0保存顺序，StockGroupCommon保存系统自选股注册。读取顺序引用的普通自建分组；带选股公式的记录单列排除，不把“1、趋势、昨日炸板”等查询缓存混入自建组。新建普通组从当前目录发现，无须在历史名单出现过。

系统“自选股”的成员可能未缓存在此处。注册证明其固定前缀身份即可；成员记unknown，不填空集。它不参加普通组排名，也不由本流程自动改成员，不为补齐它扫描UI。只有用户另有维护该组成员的任务才局部读取它。

## 日常读取

从实际技能目录解析脚本路径，输出写到本次运行目录的绝对路径：

```text
python3 ABS_SKILL_DIR/scripts/local_groups.py snapshot --output ABS_RUN/local_before.json
```

快照包含 `order`、`groups`（成员代码、市场、数量、文件证据）、`group_snapshot`及排除的查询缓存。分类4.0直接使用其 `group_snapshot`，`source=local_file`；旧字段 `ui_total`兼作目录总数，不声称读过UI。程序在本地计算差集和涨停数，只给模型目录、相关代码及结果摘要，不输出全量成员明细。

不得将文件mtime或版本号单独当作保存成功。源失败不产生空名单、不移除连板、不强排；不以旧共享档案冒充本轮读取。正常入口不再另做UI目录或成员盘点。UI动作中识别当前组选中和精确证券，是操作定位，不是重新盘点。

研究后、真正写入前刷新一次本地快照作为before，吸收用户期间的手动变动；只更新目标差集，不重做已完成研究。同组短批次保存后取得的成功快照可作为下一批的before。

## 保存后的唯一一轮确认

实际点击外层确定、观察保存完成后，记录真实 `saved_at`，准备期望文件。以下仅为格式示例：

```json
{
  "settings_saved": true,
  "saved_at": "2026-10-27T15:40:00+08:00",
  "changes": [{"group": "目标组", "code": "000001", "action": "add"}],
  "targets": [{"group": "目标组", "code": "000001", "present": true}],
  "created_groups": []
}
```

```text
python3 ABS_SKILL_DIR/scripts/local_groups.py verify --before ABS_RUN/local_before.json --expect ABS_RUN/expected.json --output ABS_RUN/saved_receipt.json
```

- `changes`只放实际发生的add/remove；脚本按“修改前集合＋这些变动”检查改动组的完整代码集合与数量，确认没有多加、多删。新组写入 `created_groups`，其初始集合为空。
- 已存在的分类目标用 `targets`确认，不再在UI中逐股预查；双分类两个组各写一个目标。
- 连板最终集合用 `exact_groups={"连板":[完整目标代码]}`。全部目标保存确认后才允许移除错误源组；移除后的最终targets同时列出全部有效目标仍存在，与源组不存在在同一次文件读取中确认，两个阶段各保留必要回执。
- 排序用 `order=[完整目标组序]`，保存后本地完整顺序逐项相等才成功；不再重开设置读取全序，也不重扫成员。
- 无修改时用 `no_changes_needed=true`、`settings_saved=false`，照常从当前文件确认目标/顺序，不强制保存或启动UI。
- 正常一次匹配即结束。仅不匹配时默认最多8秒、间隔0.5秒重读本地文件，等待异步落盘。超时只报告具体目标/集合/顺序缺口；源失败不能填0。
- 文件确认失败后才允许对缺口做一次局部UI确认；有UI证据则明确记 `ui_targeted_readback`，不扩展到未改组，不重放整批。仍失败记pending，继续独立项。最终组序只有本地无法确认时才从左表读一次，不读右侧成员。

回执 `pass=true`、逐目标检查成功及证据快照是本地确认依据。分类逐目标回执使用 `verification_method=local_file_after_save`（无修改时local_file_current）、`local_file_receipt=ABS_PATH`、`verified_at`及 `readback_verified=true`。`readback`表示实际读取客户端保存文件，不伪装成UI读取。分类校验器会检查本地回执确实成功且覆盖该代码/该组。

UI高频操作统一由 [操作函数](operation-functions.md) 的 `saveBatch`/`applyGroup` 生成期望，再调用本协议的verify。`saveBatch({verifyTargets,exactGroups})`可把删除后有效目标保留、连板完整名单并入同一确认，不再走UI检查。`confirmSaved`只接收成功且覆盖本批目标、改动组数量、完整集合和排序的本地回执；不以函数返回added或保存按钮点击成功代替文件确认。成功回执的snapshot_path所指快照直接作下一批基线，无外部变动依据时不重复snapshot。

## 检查上限与断点

每个修改批次一次保存确认；连板新增、移除按必要前置关系分阶段；最终排序一次确认。已成功的目标不重复检查。删除排序前额外数量检查、排序后全组成员重读、全局关系总数对账及多轮人工压缩包校验。保留必要的分类字段校验、实际变动确认和最终顺序确认。

本地读取与回执保存在当日运行目录作为证据和断点，不另维护一份跨日“当前成员主档案”。恢复时重新读客户端文件，再补实际仍缺的动作。只编辑本协议和脚本不触发Computer Use清理。
