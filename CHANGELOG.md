# 更新记录 / Changelog

## 2026-10-27 — 本地读取、保存确认与可复用控制器

- 新增只读 `local_groups.py`：解析客户端当前目录、成员和顺序，排除条件选股查询缓存；新普通组无需历史白名单。系统自选成员未缓存时明确为unknown，不伪造空集；多个来源不猜账号。解析适配macOS同花顺5.3.4格式，不写客户端数据。
- 新增 `ui_ops.mjs`：同一控制器复用当前主窗口，按精确组名、代码、名称和沪/深/北市场定位；响应延迟或点击回执丢失时先观察，避免反复点击add/remove。来源不明的既有弹窗保持不动。
- 批次改为 `saveBatch → local_groups.py verify → confirmSaved`：确认目标、改动组完整集合与数量，新组及最终顺序；成功快照成为下一批基线。未决动作或未通过本地确认时不放行下一批，新增确认前不删除源关系。移动删除后同时确认全部有效目标仍在。
- 无变化可只读确认，不启动UI或强迫保存；文件短时落盘不匹配采用有界重读，仍不符才局部UI核验。排序不再要求重新扫描所有成员。
- 分类交接清单增加明确market、待补市场标记和函数路由；分类校验器读取本地目录/目标回执，拒绝缺失、失败、错目标或时间被改写的证明。保留原有三源研究与单/双主分类规则。
- 公开排序工具支持系统组成员未知且固定在首位，数量保留null；普通组不完整仍阻止排名。固定前缀继续由调用方配置。
- 新增本地解析、延迟/丢失响应、窗口来源、跨语言回执、双目标保留和连板完整集合等隔离测试，加入GitHub Actions。测试通过不等于所有模型、工具或客户端版本均已实机验证。

维护说明：保留既有演示视频、MIT许可证和调用方可配置规则；未发布维护者个人路径、精确别名、真实分组文件、成员或运行回执。本次是公开技能包维护，不执行行情研究、真实分组修改或交易。

### 本次验证

113项隔离自动测试通过：排序17项、分类与回执49项、本地文件15项、UI控制器32项。1项需要维护者自行提供真实AX夹具的可选测试未运行。两项技能结构校验及包结构/链接/敏感信息扫描通过；本次没有操作真实同花顺分组。

### English

Read current client group files without editing them; reuse a state-aware UI controller; verify saved targets, exact deltas/counts and final order from local files. Delayed toggles are not replayed. Classification handoffs carry explicit market and operation routing, and validators check actual local evidence. No-change tasks avoid desktop control. Isolated parser, controller and cross-language tests run in CI. Custom taxonomy and fixed prefixes remain caller-configured; existing video and license are preserved.
