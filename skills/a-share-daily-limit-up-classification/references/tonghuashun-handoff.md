# 分类到UI的交接

UI点击、入口、窗口、保存和恢复的唯一操作说明是 `$tonghuashun-ui-maintenance`。这里仅约定数据交接，不绑定模型、对话ID或执行钟点。

1. 交付已冻结的D日4.0分类JSON、绝对路径与哈希、本轮本地文件分组目录及证据快照、精确股票代码/名称、动作、全部`target_groups`及源组；写前校验通过。单分类一个目标，双分类两个目标，不能从旧单值字段截断。独立研究请求到报告结束，未要求UI时不扩展执行。
2. 从本轮本地成员算出add/已有，不另做UI逐股预查；实际搜索时已是remove则记已存在，不反向点击。新增保存后优先以本地文件确认，已有目标在本地确认。move先把该码的全部目标组加入并保存逐组核验，再移出已确认错误主题组；任一目标未确认则保留源组。双分类另一有效目标和功能组不能删除。remove必须在本次授权范围，不能清空或删除整个分组。
3. 新建须完整查重、new_groups证据及授权成立；propose_group只报告、none不写。主窗口和其分组弹窗保持现有位置与大小。
4. 按 [数据契约](run-contract.md) 保存逐码逐目标组回执及保存后的核验，默认local_file_after_save/local_file_current并附local_file_receipt。每批确认本次变化和改动组数量/差集，成功即停止；本地不匹配才按UI技能局部回读，不全量盘点。双分类少一组成功仍是pending/failed；单股可保留已成功目标，但不能报全成功。研究成功与UI成功分别记状态。局部故障按UI技能恢复，继续独立可执行项。
5. 按UI技能 `references/operation-functions.md` 加载 `scripts/ui_ops.mjs`，用当前app和本地快照创建一个控制器；以manifest的execution字段为函数路由。`ensureGroup`只用于已授权新组；按组用 `addStocks`，普通单组短批次也可用 `applyGroup`。一个代码的双目标可同批加入，也可分批确认，但所有目标确认后才调用 `removeStocks`。删除批次 `saveBatch({verifyTargets})` 纳入全部有效目标为present=true，和源组不存在一起用同一文件回执确认，不回UI重复查目标。控制器复用于本轮后续连板和排序。
6. `saveBatch`返回expectation，写入本轮绝对路径；调用UI技能 `local_groups.py verify --before BEFORE --expect EXPECT --output RECEIPT`，再把成功回执及其snapshot_path所指快照交给 `confirmSaved`。confirmSaved只接受本地成功回执；局部UI确认另存真实UI证明，受影响批次记断点，不伪造本地成功。下一独立项可按UI技能刷新局部状态后继续。已有目标可直接本地确认，不启动UI或强制保存。
7. 股票输入要求精确code/name/market；market缺失时从本轮行情原始记录或可靠代码表补齐并记来源，不能按代码首位猜沪深或将北交所归深市。不同对话只交接文件和轻量checkpoint，不交接旧元素编号、旧app对象。
8. 调用方工作流可继续调用UI技能刷新连板和排序；本分类技能不自行读取交易或发送到固定档案对话，也不额外启动清理。
