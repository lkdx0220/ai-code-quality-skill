# 实施与验收任务（r03 / 服务首批候选）

## 最新状态（2026-10-26，0.6.0rc1）

- [x] T01–T28 已逐条建立运行证据索引，完成本候选开发验收；见[最终矩阵](final-matrix-0.6.0rc1.md)。
- [x] Claude/Kimi 两真实宿主九工具、真实失败/缺工具、大结果、60s核心截止、5s客户端取消和服务强杀恢复。
- [x] Windows真实ACL/Linux普通UID只读、两平台混合容量叠加写锁、state迁移与owner守卫、进程边界及可调新鲜度期限。
- [x] 产品固定为4a349686的冻结包，CI九项全绿；本轮仅验收和文档，没有产品修改或包重建。
- [ ] 确认发布渠道和最终版本；公开固定版本安装复验后同步规格并归档change。

下方阶段记录保留其当时结果；其中“仍待验/未commit”等历史表述不代表上述最新状态。
完成范围限最终矩阵注明的配置，不以skip、SDK回环或静态审核替代实际宿主/故障验收。

## 0. SpecDD
- [x] 读取仓库、保留源基线；收到用户转交DeepSeek文件及GLM正文的独立审核。
- [x] 核对源码，逐项处理M01–M13/A1–A3和补充意见，直接修订proposal/design/spec。
- [x] 用户转交DeepSeek/GLM的r02静态复核，均“可实施”；r03补全N项默认/边界决定，不冒称r03独立签署。

## 1. 实施前调查与原型
- [x] 独立venv安装mcp2.3.0并跑SDK loopback：initialize/tools/list、双份结果相等、领域fail非isError、并发异步响应；见phase1-preflight.md，非真实宿主验收。
- [x] Windows机制原型：先挂起再纳入Job，取消/超时/owner强杀均确认进程句柄退出；非产品恢复逻辑验收。
- [x] WSL Ubuntu进程组原型：正常取消无运行后代；强杀owner后确有存活后代，随后清理。证明恢复阻断的必要性，未实现恢复守卫。
- [x] 十万条合成清单流式输出14.2MB、汇总126B；仅验证序列化规模，不替代真实核心枚举/新鲜度计时。
- [x] SDK版本/许可证/Python/协议与输出限制核查：mcp2.3.0、协议2025-11-25；0.6.0rc1包与依赖许可见release-readiness，Claude/Kimi真实九工具及输出/期限见final-matrix；ZCode仅历史连通性，VS Code未记通过。
- [x] Windows suspended-create/Job Object、Linux正常清理和强杀后恢复阻断原型；Windows产品路径已测，Linux产品Service真实SIGKILL/同state及跨state残留阻断4/4通过（受控子命令注入，非stdio宿主强杀），见linux-recovery-readonly-validation.md；完整T08仍按矩阵保留。
- [x] initialize冷启动及异步调度原型；0.6.0rc1两平台四组安装包SDK initialize<5s，既有异步查询/取消回归通过；无SDK核心两平台明确exit2且stdout无日志。见release-readiness-0.6.0rc1.md；不代替完整宿主期限矩阵。
- [x] 大仓库inputs汇总/流式清单原型：32,000真实文件，9,312,754字节完整清单/743字节摘要，120s配置下逐文件和总摘要均核对通过；不代替产品分页/新鲜度验收。
- [x] 固定CLI现有行为及来源输入摘要：doctor-before/scan-before与cq-mcp-before-20261025基线已保留，核心修改逐项留痕。

调查时核查本机Claude Code2.1.203、VS Code1.141.2命令可用；后续构建安装、SDK与宿主结果按各自版本保留，最新配置见final-matrix。原型未被计入T01–T28产品验收通过数。

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
- [x] 构建安装子集：wheel/sdist构建成功；缺MCP extra时明确exit 2；Windows/Python 3.13和Linux/Python 3.11全新venv安装wheel/sdist并完成SDK ClientSession stdio九工具回环。证据见`audits/cq-mcp-build-20261025-01/build-install-report.md`、`audits/cq-mcp-build-20261025-02/build-package-review.md`及`audits/cq-mcp-host-20261025-01/host-and-linux-validation.md`。
- [x] 真实宿主验证：本候选Claude Code2.1.203、Kimi Code桌面1.1.3.0完成九工具、失败/缺工具/大结果、长gate/diff、客户端期限和断开取消矩阵，原始stdio核验通过；Kimi wire版本0.0.0另记。ZCode仅历史连通性子集；VS Code未记通过。见final-matrix。

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
- [x] 本候选开发矩阵证据完成，T01–T28逐项索引见final-matrix；Windows/Python3.13、Linux/Python3.11安装/故障/权限/容量，Claude/Kimi真实宿主完成。必验不以skip顶替，不声称所有客户端/协议、Windows真实满卷或最大665s宿主等待已测。
- [x] 0.6.0rc1具体候选的构建内容、许可证、依赖闭包、版本、README/工具面复验通过；内部change记录不入sdist，LICENSE/NOTICE入包。两平台wheel/sdist四组SDK九工具、质量失败/缺工具/取消和45文件来源核对通过，见release-readiness-0.6.0rc1.md。此勾选只覆盖本候选包预检，不关闭完整发布矩阵或批准渠道。
- [ ] 用户可审阅候选包与发布说明后确认渠道；公开固定版本安装复验与回退说明。
- [ ] 验收完成后同步现状规格并归档change。

## 2026-10-26 验收增量

- 发布预检：0.6.0rc1独立包与许可证完成；首次真实Linux工具链验收暴露venv Python被resolve成基础解释器，已修复并以CLI/env/config/default四组真实venv独有模块反验（修前4失败，修后4通过）。Windows最终452通过/16跳过，Linux458通过/10跳过，覆盖率84.08%，A门exit0；各平台wheel/sdist SDK九工具、真实质量失败/缺工具/实际取消通过。剩余宿主期限、Windows ACL、混合故障等逐项见release-readiness-0.6.0rc1.md，未擅自降级或关闭。

- T12/T19/T24 宿主增量（提交 ab3d484 构建包）：Claude Code 2.1.203 与 Kimi Code 1.1.3 原生 MCP 各11次调用，通过200条finding分页、72124字符占位分块、233435字符diff快照、35秒注入响应延迟及真实pytest子树主动取消。另验证Claude宿主强杀后的cancelled，以及Kimi服务强杀后宿主自动重连得到interrupted；未重提扫描，四state最终预留0，旧证据未变。详见host-acceptance-ab3d484.md；35秒为传输等待而非核心计算，完整T19与发布矩阵仍保留未完成。

- T08/T26 子集：新增Linux真实进程强杀测试4/4通过；提交后未spawn及运行中窗口、同state及跨state竞争均覆盖，残留存活时CLEANUP_FAILED，清理后interrupted，同key不重跑。
- T16 子集：普通UID65534及真实只读权限负控通过；gate历史/当前验证、diff、快照读取均成功，项目41文件及Git状态不变，旧CLI写盘exit4。
- 证据、首轮失败及未跑边界见`linux-recovery-readonly-validation.md`；产品代码未改，完整T08/T16/T26未勾选通过。
- T22 容量增量：Windows/Python3.13 与 Linux/Python3.11 各五项压力场景加一项真实八进程竞争全部通过（合计12，无skip）。1000小任务、第1001拒绝；10000游标、第10001拒绝；100次8MiB快照尝试接受29/拒绝71；三轮八连接及一轮八进程竞争不超卖；耗尽时实际子进程仍可取消并确认清理，已有结果可读。测试方法、缩小容量夹具及非stdio边界见`capacity-validation.md`。未改产品配额；完整混合负载/物理磁盘满/清state与owner流程仍待验。
- T05/T08/T11/T23/T26 故障增量：Windows、Linux 各31项通过（5个真实stdio owner强杀场景+26个存储故障）；Linux私有32MiB tmpfs实际ENOSPC两项通过。未提交事务回滚、已提交任务不重放、Windows子树回收/Linux残留阻断、旧证据保留均验证。精确窗口的测试屏障与未修改入口黑盒区分见`fault-recovery-validation.md`。
- 修复 `Store.transaction` 连接建立在try外导致错误未结构化的问题；Windows最终回归384项通过、无skip（排除单独分批压力/POSIX/磁盘模块），ruff/format/mypy通过。未重跑完整自扫/A门，未改正式.cq。
- [x] T07 故障期限定向修复：只读连接不抢写锁、控制busy等待100ms、审计独立线程/OS互斥等待50ms；真实RESERVED/EXCLUSIVE锁下查询/取消受理<1s。跨实例轮询不等锁，期限检查不再被5s轮询挡住。详见control-channel-fixes.md；不据此关闭完整T07。
- [x] 物理满盘本owner回收定向修复：按job_id发内存取消信号，state实际ENOSPC仍回收子树；无法落盘返回独立标记及warning，终态保留本owner内存，空间恢复后查询触发终态/预留原子补记。跨实例不可写仍明确失败；pending时真实stdio owner强杀后保守恢复interrupted，不宣称内存事实可跨重启保留。

## 本轮边界

控制修复独立审核的后续项：
- [x] Kimi F-01：主操作失败后rollback/close二次错误保护及结构化回归。
- [x] GLM F1：pending补记成功直接返回提交快照，避免追加读取误报未落盘。
- [x] GLM F2：queued→running短暂STATE_BUSY有界重试、可取消、不越总预算、不提前spawn。
- [x] GLM F3（既有，后续专门批次已修复）：同项目执行锁及旧进程域核验后，当前state旧op-*与新接纳同事务恢复；job/证据/其他state不删，不按年龄/PID消失回收。见operation-recovery-validation.md；不计入前一批三项修复。

F3专门批次：新增30项，其中每平台12个真实stdio owner强杀窗口；Windows最终440通过、
Linux故障恢复93通过，均无skip；配额竞争/控制子集两平台各3通过。
自扫覆盖率4037/4803=84.0516%，相对控制审核后续自扫新增0/修复0/仍存在7/豁免1，
diff exit0、A门仍因既有blocker/high exit1。完整宿主/发布矩阵仍待验，未commit/push/发布。

处理表与证据见control-review-followup.md。Windows410/0 skip、Linux故障恢复63/0 skip；
最终加强启动断言补验Linux5通过，Windows最终自扫再次覆盖普通全回归。
覆盖率4022/4792=83.9316%；相对控制修复自扫新增0/修复0/仍存在7/豁免1；
diff exit0、A门因既有blocker/high仍exit1。原报告/冻结包未改，修订候选未再次独立签署。
r03规格、阶段1原型、核心和服务候选分开记录。核心317项加服务36项为353项历史完整回归；此前故障批次Windows384项及容量两平台12项见各自报告，不与后续重复计数。Windows/Linux构建安装、SDK stdio及三个真实宿主连通性子集不冒充T01–T28全矩阵通过。

## A门收尾（2026-10-26，最新源码状态）

- T01/T17 CI增量：旧workflow缺MCP extra且SDK存在性检查被tests/mcp namespace误导，远端19项导入失败。现拆分核心无依赖与带extra三平台矩阵，两平台dogfood安装extra。Windows核心351通过/113跳过、MCP452通过/12跳过；Linux MCP454通过/10跳过，均无失败。远端复验按修订提交Actions另记，见ci-validation.md；不因此关闭完整发布矩阵。

- [x] 两项既有A门阻断定向处理：注释假凭据移除；内部参数数组校验/复制和POSIX显式shell=False。新增12项真实参数边界测试；未改检测规则、阈值或.cq。
- [x] Windows自扫452通过/12默认跳过；Linux受影响进程/服务/崩溃恢复87通过/1 Windows专用跳过；静态全过。覆盖率4047/4811=84.1197%；diff新增0/消除2/仍存在5/豁免1，diff和A门均exit0。
- import-linter无契约配置仍skipped，不计通过；完整T19及发布项继续保留未完成。旧红门记录为历史结果；最新源码验证详见a-gate-validation.md。本批尚未commit/push/发布。

2026-10-26控制修复增量：Windows回归398 passed/0 skip；Linux故障/恢复51 passed/0 skip；最终字段及受影响压力子集补验Windows7/Linux10通过。并发审计/同时完成取消/两种写锁读取共4场景连续6轮均通过（24次执行，不是全矩阵六遍）。真实stdio新增pending终态写失败后owner强杀恢复窗口。根因、首轮失败及证据见control-channel-root-cause.md和control-channel-fixes.md。

自扫run cq-mcp-control-selfscan-20261026-01：7工具ok、import-linter无配置skipped、consistent；覆盖率3985/4756=83.7889%。相对service-20261025-03新增0/修复0/仍存在7/豁免1；diff exit0，A门因既有blocker/high仍exit1。正式.cq未改。检测能力由底层工具提供，cq聚合编排。

已复现的控制写锁期限及本owner满盘回收差距已定向关闭；完整T07/发布矩阵不关闭。其余崩溃排列、宿主失败/大结果/长调用/断开全链、容量混合故障与清state流程/Windows只读ACL、许可证/依赖发布复验仍待验。另一实例无法读取owner内存终态、不可写时无法持久化跨实例取消的边界已明确；pending丢失的重启不假称找回精确终态。用户转交的复核不冒称本会话调用；本次未调用外部模型、未commit、push或发布。
