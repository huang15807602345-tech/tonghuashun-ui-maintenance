# 数据、断点与验收契约

## 目录和日期

根目录由调用方传入；缺省为当前工作目录，不能回退到某位用户的旧项目路径。`scripts/init_run.py --date D --root ABS_ROOT` 创建 `market_history/work/limit_up_classification_YYYYMMDD/`，包含raw、evidence、outputs、receipts及run_manifest.json。总流程运行时在其run_state.json保存此绝对路径；换对话续作传入同一路径。脚本从实际技能目录解析。

每阶段记录状态、输入/输出哈希、实际时间和错误。输入与成功回执一致才复用；UI仍须看实时状态，避免重复点击。原始材料和旧产物保留，不覆盖为新日期或空结果。同一运行目录不并发写；工具报发送/点击成功不表示业务完成。

## 分类JSON（schema_version 4.0）

完整合成示例见 [classification](../examples/minimal-valid-classification.json)。旧2.x/3.x产物只支持历史最终验算；新一轮pre-ui必须迁移为4.0，补齐置信度、候选主分类活动统计与单/双目标，不改旧回执冒充本次。

双分类合成示例见 [双目标分类](../examples/dual-valid-classification.json) 及 [逐目标保存回执](../examples/dual-valid-ui-audit.json)。示例仅用于格式与离线验证，不是实际股票研究或UI操作证据。

顶层：`trade_date`、`scope=non_st_final_limit_up`、`generated_at`、`source_policy`、`population`、`group_snapshot`、`new_groups`、`theme_activity`、`rows`、`summary`。

- `source_policy.minimum_reason_websites`至少3，`st_detail_policy=exclude_before_detail`；来源开放，选股宝/东方财富/同花顺是优先来源，不是封闭白名单。
- `population`包括 `status=reconciled`、`final_data_verified=true`、至少两个已核验名单来源的`source_counts`、`non_st_count`、`excluded_risk_warning_count`、完整`codes`、`codes_sha256`和无未解决差异的`conflicts=[]`。失败来源单列`source_failures`，不填0。哈希算法为排序后的六位代码用换行连接、无末尾换行的UTF-8 SHA-256。真实零只还须`empty_confirmed=true`。
- `group_snapshot`日常来自本次客户端本地文件（`source=local_file`），由UI技能的local_groups.py输出，包含`captured_at`、完整精确`groups`、`ui_total`、`complete=true`及绝对`snapshot_path`。校验器核对证据快照与目录一致。`ui_total`沿用旧字段名表示目录总数，不声称读取UI；异常局部恢复可保留live_ui来源。共享历史档案不作当前来源。
- `new_groups`每项记录`name`、完整`members`、`not_reusing_reason`、具体`market_linkage_evidence`及`creation_authorized`。members仅为本次最终名单内拟写入股票；linked_members列出当日或近十交易日已核验的相关活跃股票，可含不在本次最终名单的代码作为联动证据，不自动写入这些代码。一般至少两只linked_members，不能要求本日同时涨停两只才允许复用/建立合理分组；真正只有单股证据的例外在用户明确要求时用`user_requested_singleton=true`并保存原始授权依据。不得用普通业务标签绕过建组条件。

每行保留`code/name`、连续板数及其依据、封板时间和精度、`source_reasons`、业务基础、即时催化、`market_context_evidence`、最终交易原因、个股放大器、`reason_selection`、`classification`、`evidence_status`、`ui_plan`。

实际UI证券输入另需明确`market`（SH/SZ/BJ，或UI技能认可的等价值）及来源，可直接保存在行内。缺失时manifest标记待补，从本轮原始行情或可靠代码表补齐，不重做原因研究、不按代码首位猜测。该补充不改变4.0分类目标数组。

### 原因材料

每个网站一张证据卡；不能用同网站不同子域/多个页面凑数量。键名可为实际来源。每张卡包括：

- `status=complete/partial/missing/error`，`concepts`与原始`reason`。
- 原页`url`、带时区`retrieved_at`、实际原因所属`reason_date`。
- `material_type=daily_limit_up_reason`与`verified=true`仅在原页实际核验后填写。搜索摘要、F10长期主营/概念标签、无日期异动提醒不够。
- `provenance.kind=original/reprint/unknown`；转载须`original_url`，保留转载关系，不将转载视作独立因果印证。

待写主题组的每股至少三家不同网站的完整、已核验、对应D的原因材料。第四家缺口不否定已有三家的可用材料，但要保留缺口；不足三家则未分类、待核验，不产生主题写入。`collect_ths_f10.py`只辅助抓取，缺少明确日期会标partial，采集完成不等于`verified=true`。该脚本要求代码清单日期与请求D一致，缓存保留原采集时间；复用旧缓存不伪造新采集时间。

### 判断与动作

`reason_selection`保留来源选择、原因、反证，增加`initial_confidence`、最终`confidence=high/medium/low`和`confidence_basis`。任一候选曾为低时记录`low_confidence_triggered=true`；不能抹去补查前的低判断。置信度按分类契约的实际归因标准评，不是收益概率。

低置信度必须有`exploratory_research`：`status=completed/unresolved/blocked`、`questions`、`searches`（逐次`query/channel/evidence_refs/findings`）、`conclusion`和`trend_analysis`。走势分析为completed时保存`candidate_groups/representatives/time_range/granularity/evidence_refs/observations/market_comparison`；确实无法取得时用unavailable并写`attempted_channels/limitations`。高/中不强制额外完整分时研究，但须有实际短线归因依据。

`classification`保留`status/basis/alternative_groups/existing_wrong_groups`，增加`mode=single/dual/none`及权威目标数组`assignments`。每项有`primary_group`、精确`target_group`、`market_trading_reason`、`confidence`、`confidence_basis`、`relation_tier`、`basis`、`evidence_refs`。single一项，dual恰好两项且每项中高置信度，另写`dual_basis`解释为何难分主次；none为空数组。单分类的旧`primary_group/target_group`字段与唯一assignment保持一致；双分类旧单值字段为空，防止执行器只读第一个目标。

每码一个`ui_plan`，动作`add/move/remove/propose_group/none`，`target_groups`与全部assignments精确一致。单分类可保留一致的`target_group`别名，双分类该单值为空。移除端为`source_groups`，不能含功能组或任一有效目标。move先使**所有目标**保存核验成功，再删错误旧组；任一目标失败时保留源组。manifest保存全部`target_actions`与删除前置条件，不能展开为两个会相互删除的独立move。

未分类：`mode=none`、`assignments=[]`、单值主组/目标为空、`target_groups=[]`及`ui_plan.action=none`，填写`unclassified_reason`与`unclassified_kind=independent_event/insufficient_evidence/policy_excluded/weak_linkage/niche_excluded/theme_activity_pending`。报告末尾分别解释纯事件、三源缺口、补查后仍低置信度、小众规则排除和统计条件待核实，保留已查线索与现有组状态。

### 可复用的板块统计与排除

顶层`theme_activity`按规范主分类名存储，每个方向只算一次：

- `mapping_basis`说明主分类粒度与映射依据；按调用方已确认的分类粒度与别名配置归并，不预设维护者个人分类。
- `today={status,codes,evidence_refs}`：verified时为D日全市场最终非ST涨停中的该主题代码，唯一且完整。
- `history={status,trading_dates,calendar_verified,codes,evidence_refs}`：verified时为含D最近十个真实交易日、十日全市场最终名单与归因的去重代码，包含D该主题代码；日历与映射证据须留档。
- `niche={value,basis,evidence_refs}`：value为true/false/null，评的是“极小众偏门且几乎无逻辑驱动”，保存支持和反证。
- today/history无法完整取得时用`status=unavailable,codes=null,gap=具体缺口`，不能给0或空数组伪装完整。
- history已核实至少三个不同代码时，可用`status=verified_at_least_three`，保留十日交易日期与日历证明，`codes`仅为已核实子集，另存`occurrences=[{code,date,evidence_refs}]`逐股证明日期、最终涨停和主题归属。它只能证明第三项为false，不能声称总数恰好为3。已被其它条件决定、无需查询的统计可用`status=not_needed,codes=null,gap=不影响判断的原因`，按unknown参与计算，不能据此作低数量排除。

每股`theme_filter_results`按候选主分类记录`include/exclude/pending`。校验器从原代码集合重新计算：D日去除自身后0只、niche为true、十日去重小于3只，任意两项已证实true即exclude；已证实true不足2且加上unknown可能达到2为pending，否则include。采用的每项assignment必须为include；两个方向分别检查，排除一个不连带否定另一个。纯事件且没有候选板块时可为空对象。历史缺失不能等同排除，但可能使需要判断的方向保持待核实。

## UI回执

manifest的`execution`声明UI技能、模块相对路径、函数路由和保存确认顺序。加载一次 `scripts/ui_ops.mjs`，普通动作复用同一控制器；不保存函数对象或固定AX编号。`saveBatch`产出的期望与成功本地回执分别存入本轮绝对路径，`confirmSaved`后更新基线。移动后的最终确认须同时含全部有效目标存在与错误源组不存在，不能仅确认删除。此要求并入原批次文件确认，不额外启动UI检查。

示例见 [ui-audit](../examples/minimal-valid-ui-audit.json)。绑定`trade_date`与实际分类文件的SHA-256。

- `preflight`只检查`main_window=true`、`window_layout_preserved=true`、`group_dialog_verified=true`。不要求最大化或重复点击入口。
- `by_code`保存对应动作和总体`status=already_present/added/moved/removed/failed/pending`、`verification_method/verified_at/readback_verified`。4.0成功项还必须有`targets`数组，逐目标保存`target_group/verified_target_group/status=added或already_present/verification_method/verified_at/readback_verified=true`，一个成功不能代替双目标成功。move/remove另记`verified_absent_source_groups`；全部目标确认后才能删除源组。
- 实际变更须外层保存后读取客户端本地文件确认，`settings_saved=true`；正常不重开UI盘点。方法固定为`local_file_after_save`，逐目标附`local_file_receipt=ABS_PATH`，回执必须pass=true并覆盖代码/组；校验器会读取该回执。其`readback_verified=true`表示文件回读。无修改用`local_file_current`及`no_changes_needed=true`；可用`execution_mode=local_read_only_no_changes`，不伪造UI预检，不强迫保存或启动UI。来源缺失/不一致才局部UI回读，明确记ui_targeted_readback。检查协议见UI技能references/local-files.md。
- 失败/pending保留`reason`。缺回执、错目标、缺核验材料都不能记UI完成。

`build_ui_manifest.py`生成动作时内部执行pre-ui校验；不要再手动重复跑同一份数据。独立研究的写前检查可用`validate_classification.py --input ABS_JSON --stage pre-ui`。写后用`--stage final --ui-audit ABS_AUDIT --strict-ui-success`判完整完成；不加strict只检查回执结构，存在pending/failed仍不是业务完成，必须查看`ui_all_success`。

最后文字逐股覆盖全部非ST最终名单，列出主原因、单/双主组、逐组置信度与真实UI结果。末尾单列未分类、排除及失败项，包含补查/走势分析、数量窗口和实际缺口。summary按股票计数，双分类仍是一只；另可报主题关系数。排序一股在两个不同组各计一次，组内按代码去重，连板名单仍每码一次。详细来源留JSON/可选MD，不生成HTML。UI恢复只查UI技能。
