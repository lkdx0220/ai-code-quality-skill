# 实施与验收任务（r03 / 服务首批候选）

## 0. SpecDD
- [x] 读取仓库、保留源基线；收到用户转交DeepSeek文件及GLM正文的独立审核。
- [x] 核对源码，逐项处理M01–M13/A1–A3和补充意见，直接修订proposal/design/spec。
- [x] 用户转交DeepSeek/GLM的r02静态复核，均“可实施”；r03补全N项默认/边界决定，不冒称r03独立签署。

## 1. 实施前调查与原型
- [x] 独立venv安装mcp2.3.0并跑SDK loopback：initialize/tools/list、双份结果相等、领域fail非isError、并发异步响应；见phase1-preflight.md，非真实宿主验收。
- [x] Windows机制原型：先挂起再纳入Job，取消/超时/owner强杀均确认进程句柄退出；非产品恢复逻辑验收。
- [x] WSL Ubuntu进程组原型：正常取消无运行后代；强杀owner后确有存活后代，随后清理。证明恢复阻断的必要性，未实现恢复守卫。
- [x] 十万条合成清单流式输出14.2MB、汇总126B；仅验证序列化规模，不替代真实核心枚举/新鲜度计时。
- [ ] SDK稳定版本/许可证/Python/协议、两个真实客户端及输出限制核查。
- [ ] Windows suspended-create/Job Object、Linux正常清理和强杀后恢复阻断原型。
- [ ] initialize冷启动及异步调度原型；SDK缺extra兼容。
- [x] 大仓库inputs汇总/流式清单原型：32,000真实文件，9,312,754字节完整清单/743字节摘要，120s配置下逐文件和总摘要均核对通过；不代替产品分页/新鲜度验收。
- [x] 固定CLI现有行为及来源输入摘要：doctor-before/scan-before与cq-mcp-before-20261025基线已保留，核心修改逐项留痕。

已核查本机Claude Code2.1.203、VS Code1.141.2命令可用，尚未接入cq MCP；Linux仅WSL机制原型，构建包和原生Linux/双宿主/实际大仓库仍待验。原型未被计入T01–T28产品验收通过数。

## 2. 实施顺序
- [x] 核心run ID/显式空adapter校验、错误映射、config快照字段、doctor来源修正；214/214回归，含未知adapter旧exit1守卫。
- [x] 核心共享inputs枚举与命令、发布marker、gate/diff --no-save、脱敏扩规则；写入中断/损坏/身份/IO负控见tests/mcp/test_core_evidence.py。此项不代表MCP读取/分页已实现。
- [x] 两位核心r01独立审核逐项处理；schema降级/UTF-8损坏/读取越界/Windows别名/脱敏摘要/adapter集合回归修复，完整260项通过（原214项+46项新反例）。处理表reviews/core-r01-disposition.md；复验见core-review-fixes.md，不冒称修订候选已获独立复核。
- [x] 两位核心r02独立复核已收：GLM允许进入，DeepSeek要求修复。具名baseline越界/损坏、异常文件名及scan/gate/diff脱敏已补；skipped统计说明修正，coverage承诺纠正。完整317项通过（tests/mcp=136），详见core-r02-followup.md。T10最终verdict/T13可信来源仍未实现。
- [x] MCP协议/启动策略、SQLite台账与OS锁、九工具schema首批实现；SDK握手及九工具实跑，不替代宿主验收。
- [x] 异步doctor/scan、总期限、取消和进程域首批实现；Windows真实残留子树、owner强杀恢复及取消竞态测试；Linux产品路径仍待验。
- [x] run_header/verdict/comparability、分页/快照/发现/容量首批实现；skipped不能通过、历史/过期/超时、未知版本不可比、大finding/diff及配额反例通过。
- [x] docs/mcp.md、README与通用启动示例更新；候选声明mcp2.3.0/pywin32 312，无本轮安装。
- [x] 文档、CLI/Skill回退；README、docs/mcp.md和通用启动示例已更新。
- [x] 构建安装子集：wheel/sdist构建成功；缺MCP extra时明确exit 2；Windows/Python 3.13全新venv安装wheel[mcp]成功；真实SDK ClientSession stdio九工具回环通过。证据见`audits/cq-mcp-build-20261025-01/build-install-report.md`及服务E2E目录。
- [ ] 真实宿主验证：Claude Code、VS Code尚未接入并实跑；长gate/diff、宿主期限和断开取消仍待验。

## 3. 验收矩阵

| 编号 | 需求 | 必验行为 |
|---|---|---|
| T01 | CQ-MCP-01/13 | core-only旧CLI可用，缺extra明确报错；extra安装后协议初始化正常 |
| T02 | CQ-MCP-01/03 | 九工具、未知键拒绝、stdout无日志；initialize<5s且不等慢解释器探测 |
| T03 | CQ-MCP-02 | 中文/空格；../盘符/UNC/设备名/尾点空格/junction/大小写别名；audits/state/用户锁分别归属；同用户跨state同锁 |
| T04 | CQ-MCP-04 | 默认五项/可选两项/受控pytest枚举对齐；空/重复/越权拒绝；CLI空串/API[]/get_adapters([])不执行pytest；None兼容 |
| T05 | CQ-MCP-05 | 同key并发同job、异参冲突；跨state只互斥；终态重用和换key重跑；事务超时STATE_BUSY |
| T06 | CQ-MCP-06 | 同秒不同UUID、受理即返回run_id但pending不可读取；预置目录不覆盖、核心路径校验、RUN_COLLISION/exit3、身份一致 |
| T07 | CQ-MCP-07 | 正常/单工具timeout后残留树回收；queued取消/完成竞争；get/cancel受理<1s；宽限失败阻断 |
| T08 | CQ-MCP-07 | Windows强杀后核查安全恢复；Linux强杀残留阻断；PID重用不误杀；OS锁释放与进程域存活分离 |
| T09 | CQ-MCP-08 | scan0/1/2/3/4、doctor0/2、gate0/1/2/3/4、diff0/1/3/4；IO4优先且保留underlying exit；inputs阶段无发布与工具exit2区分；错误码全集一致性 |
| T10 | CQ-MCP-08 | 默认五项齐全而无可选工具/配置→pass_with_gaps；显式选缺失工具、全/部分skipped、显式disabled→runtime gap/cannot_judge（可信质量失败优先）；不可照搬core passed；false→pass_historical且保留gaps；stale→pass_stale；超时/unstable→cannot_judge；tools_ok及不可比基线不误标fail |
| T11 | CQ-MCP-06/09 | 半写无marker→NOT_READY；损坏摘要→INVALID_ARTIFACT；合法空数组不同于坏JSON；旧run缺marker/run_id的unknown策略 |
| T12 | CQ-MCP-09 | 200KB占位推进/无重漏；游标内容变化/TTL/重启；artifact码点offset迭代/next_offset推进/digest变动拒绝；中文emoji转义及双份预算 |
| T13 | CQ-MCP-10 | core正常字段等价；同名baseline拒绝；具名baseline不可单独背书，核对已验证源run；ignore/config/suppression/tool版本不可比；publication未知/scan不稳定任一侧comparable=false；正常源码变动允许 |
| T14 | CQ-MCP-11 | 共享inputs规则/新增改名删除；summary摘要与完整清单一致且大清单不塞stdout；默认unknown；>60s夹具放宽期限能成功；超时FRESHNESS_TIMEOUT不静默历史通过 |
| T15 | CQ-MCP-12 | 版本化规则已知凭据含Bearer在响应/日志/快照替换；.env不被MCP读取；未知形态不写必检出断言 |
| T16 | CQ-MCP-03 | 只读项目根/audits下--no-save成功，原run hash不变；不新增项目锁、不改变git status（除原audits）；旧CLI默认写盘/IO错误；重调快照不变 |
| T17 | CQ-MCP-13 | 旧CLI/Skill/DSH接口与无.specdrift配置CI回归；新增正常字段兼容；两项行为修正公告 |
| T18 | CQ-MCP-13 | Windows/Linux构建wheel/sdist干净安装，非仅editable；UTF-8/cp936控制台验证 |
| T19 | CQ-MCP-13/14 | 两真实宿主全链/缺工具/失败/大结果；记录structuredContent/text及版本；gate/diff同步长调用/客户端期限配置/断开取消，无法支持的配置不得宣称支持 |
| T20 | CQ-MCP-14 | 可信Python仓dogfood；执行时间、返回字节、CLI对照、未执行项和失败轮如实保留 |
| T21 | CQ-MCP-02 | 启动不探测/固定解释器env/配置变化拒绝/来源正确；慢doctor协议不阻塞但scan报PROJECT_BUSY；docs顺序示例 |
| T22 | CQ-MCP-15 | 瞬态预留同事务不超卖/结算释放差额；1000小任务及100次大快照组合在明确阈值STATE_LIMIT，独立上限不保证全部接受；读取消保留；清state不删除用户锁owner |
| T23 | CQ-MCP-06 | 在summary/findings/report/inputs/coverage/marker各写入点中断，不能消费混合证据；marker包含coverage缺失状态 |
| T24 | CQ-MCP-09 | 预算内大diff→摘要+完整快照；>8MiB→OUTPUT_TOO_LARGE+回退；不读被覆盖原diff.json救场 |
| T25 | CQ-MCP-15 | 新会话分页发现本state jobs/同项目runs；legacy标unknown，列表仅marker_present不假称全摘要verified；目录/条目上限明确INDEX_LIMIT |
| T26 | CQ-MCP-05/07 | commit前后、spawn前后崩溃，任务不重跑；owner意图与OS锁恢复一致 |
| T27 | CQ-MCP-07 | 总期限小于核心预算时timed_out无结论；扫描前后输入阶段各有期限，超时无发布marker；缺结果不返回空findings；timeout_for值可追溯 |
| T28 | CQ-MCP-10/11 | Config.snapshot新增字段，rules_version和suppression摘要保存；旧字段缺失明确unknown、不假定默认相同 |

## 4. 发布
- [ ] 全矩阵证据齐全，必验不以skip顶替；静态审查不替代运行验收。当前仅有Windows/Python 3.13构建安装和SDK stdio回环子集。
- [ ] 构建包内容、许可证、依赖、版本、README与工具面一致，无私有目录/凭据/audits入包；当前只完成构建产物生成和干净安装实跑，包内容/许可证审查仍待完成。
- [ ] 用户可审阅候选包与发布说明后确认渠道；公开固定版本安装复验与回退说明。
- [ ] 验收完成后同步现状规格并归档change。

## 本轮边界
r03规格、阶段1原型、核心和服务候选分开记录。核心317项加服务36项为353项；服务实现及最终回归见service-implementation.md。Windows本机SDK与构建安装子集不冒充T01–T28全矩阵或真实宿主通过。Linux/Python3.11、双宿主长调用/断开、完整容量压力/只读ACL、包内容审查等仍待验。全量A门未转绿，正式.cq未改。用户转交的复核不冒称本会话调用；本轮未调用外部模型、未commit或发布。
