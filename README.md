# 同花顺涨停研究与 UI 分类整理

[English](README.en.md) · [研究分类技能](skills/a-share-daily-limit-up-classification/SKILL.md) · [UI维护技能](skills/tonghuashun-ui-maintenance/SKILL.md) · [MIT License](LICENSE)

面向 Mac 版同花顺日常复盘中手动查原因、逐股分组和整理自选的繁琐流程，本项目提供一套供 ChatGPT / Codex 等兼容 AI 环境使用的技能：研究当日全部非 ST 收盘涨停股，结合至少三家涨停原因网站与当天盘面联动形成题材分类，再通过桌面操作将结果写入同花顺，完成分组维护并在保存后逐项核验。

目标是让分类有证据、整理可核验。证据不足、原因冲突或独立事件会明确保留，归因结论不承诺绝对准确。

## 两个协作模块

| 模块 | 负责什么 | 主要输出 |
| --- | --- | --- |
| 涨停研究分类 | 核对完整非ST最终涨停名单；至少三家网站交叉核验；比较催化、业务与当日联动；低置信度继续补查 | 带原页、日期、置信度及缺口的分类JSON/报告、UI动作清单 |
| 同花顺UI维护 | 在确认的主窗口及其分组弹窗中加入、移除、移动成员，新建分组及排序；保存后重新打开核验 | 逐码逐组回执、未完成项与续作断点 |

执行顺序：**只读同步现有组名 → 研究完整涨停名单 → 校验分类 → 写入并回读 → 按需要刷新连板和排序**。研究可以单独使用；UI也可以只执行调用方已核实的明确名单。

## 分类与整理方式

- 优先同花顺、东方财富、选股宝，允许可靠补充来源；逐股保留原页、所属日期、原始原因与转载关系，不用搜索摘要代替原页核验。
- 结合当天启动/封板先后、代表股、共振与反证判断短线归属；不凭静态概念或收盘涨幅指定“谁带动谁”。
- 优先复用含义准确的已有组；新建须说明成员、联动规模和不复用理由。个人分组、别名和分类粒度由调用方配置。
- 一个主要原因用单分类；两个均有中高置信度且难分主次时支持双分类，两个目标都需实际保存核验。
- 对证据缺失、独立事件和默认小众规则排除分别报告，完整名单仍保留，不为每只股票强行贴标签。默认排除条件见[分类配置](skills/a-share-daily-limit-up-classification/references/classification-preferences.md)。
- UI按精确组名、代码和市场操作；先使全部目标保存核验成功，再移除已确认错误的源组。保护功能组，保留其他看盘分屏的布局。
- 连板必须有真实连续涨停证据；排序依据完整最终涨停事实，固定前缀可配置，同数保留实时顺序。缺失数据不当空集或0。

## 运行条件

需要能读取网页和保存证据的AI环境。实际维护还需要 **macOS、同花顺客户端，以及可观察和操作该电脑桌面的工具**，按工具要求配置辅助功能和屏幕录制权限。仅有网页搜索或云端代码执行的环境不能控制本机客户端；普通网页聊天也不会因安装本仓库就自动获得电脑控制能力。

本项目不包含同花顺客户端、Computer Use运行时、付费行情服务或登录凭据，也不绑定某个模型、固定对话ID或15:30执行门槛。盘中可准备；最终名单未核实前不做收盘写入。可指定交易日补跑或按原目录续作。

先阅读运行环境当前工具文档，再映射语义动作；[Computer Use接入说明](skills/tonghuashun-ui-maintenance/references/computer-use.md)中的接口仅为适配示例。

## 安装

1. 下载或克隆仓库：

   ```bash
   git clone https://github.com/huang15807602345-tech/tonghuashun-ui-maintenance.git
   ```

2. 在支持Agent Skills的环境中，分别加载`skills/a-share-daily-limit-up-classification/`和`skills/tonghuashun-ui-maintenance/`目录。Codex本地技能可将这两个完整目录放到`~/.codex/skills/`；如已有个人版本，先比较和备份，保留自己的配置。
3. 初次运行先只读盘点，确认目标主窗口与精确组名，再授权完整分类维护。运行数据与回执保存在调用方工作目录，不写回技能目录。

## 请求示例

```text
使用 $tonghuashun-ui-maintenance，只读列出当前全部自选分组名称、顺序和界面总数。
确认主窗口，保留其它看盘窗口的布局，不修改成员。
```

```text
使用 $a-share-daily-limit-up-classification，处理指定交易日全部非ST收盘涨停股。
先读取实时分组，至少三家原因网站交叉核验，结合当日短线联动分类。
校验通过后调用 $tonghuashun-ui-maintenance 写入并逐组保存回读。
缺证、独立事件及未完成项单列；保留其它看盘分屏。
```

仅要研究时明确“只研究，不操作客户端”。清空、删组及全库重整需另有明确范围；普通分类不包含这些操作。

## 离线工具与检查

Python 3.10或以上，辅助脚本仅使用标准库：

```bash
python3 skills/tonghuashun-ui-maintenance/scripts/plan_group_order.py --input skills/tonghuashun-ui-maintenance/examples/sorting-input.json
python3 -m unittest discover -s tests -v
python3 -B skills/a-share-daily-limit-up-classification/scripts/test_classification.py
python3 scripts/validate_package.py
```

研究模块包含运行目录初始化、同花顺F10线索采集、分类校验和UI清单生成工具，使用方式见[数据契约](skills/a-share-daily-limit-up-classification/references/run-contract.md)。采集器生成待核验材料，不代替完整名单获取和三源核验。JSON示例均为合成测试材料，不能当作真实研究或实际UI回执。

## 核验与限制

- 操作说明来自桌面工作流的迭代；首次公开版本不声明所有模型、macOS和客户端版本均已实测。
- 自动测试覆盖离线算法、数据契约和包结构，不证明真实涨停因果或本机写入成功。必须有当前任务的原页证据与保存后UI回读。
- 动态界面每次重新观察；连接报错后动作可能已生效，应核对现状后只补剩余差集。
- 不读取交易账户，不买卖、撤单或转账，不直接修改客户端配置数据库。交易账户未登录不作为自选维护的账户预检。

欢迎提交可复现问题和改进，见[贡献说明](CONTRIBUTING.md)。请勿上传账户、真实交易记录、个人目录或未脱敏截图。项目使用AI辅助编写与审查，客户端变化仍需实际验证。

本项目与同花顺及OpenAI无官方隶属关系，名称用于说明兼容目标。仓库原创内容采用MIT许可证，第三方客户端、网站和工具遵循各自条款。
