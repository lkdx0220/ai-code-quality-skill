# gate/diff 崩溃预留恢复

日期：2026-10-26（Asia/Shanghai）。基线HEAD：`32849e114c9ae7ee96bf86e2a6b90c86f7a95ebc`。
这是GLM F3后续作者修复与运行验证，不是新的独立审核或全规格发布声明。

## 根因与修复规则

旧gate/diff先提交op-*容量预留，最后在finally释放；强杀owner跳过finally。
SQLite事务、OS执行锁会被系统释放，但已提交reservation不会自动删除，最多每次滞留9MiB。

本轮仅新增四个产品落点：ProjectLock/Store记录规范项目身份；Store提供带lease验证的
op恢复；gate/diff接纳事务调用；job接纳存在op-*时先锁定、恢复再核算配额。
无需改台账schema、迁移旧记录、添加工具或定时清理器。

| 接纳路径 | 顺序 | 保证 |
|---|---|---|
| gate/diff | 同项目执行锁及旧域验证 → 事务内清旧op-*、预留新op-* → 执行 | 无法核验旧域则不清理 |
| 新key doctor/scan，有op-* | 查重 → 同项目锁及旧域验证 → 同事务清旧op-*、核算配额、插入新job | 旧预留不能永久挡在STATE_LIMIT前 |
| 新key，无op-* | 原配额/项目锁/插入顺序 | 保留既有正常与容量故障路径 |
| 同key重用、查询、initialize | 原只读/去重语义 | 不抢执行锁做清理、不重放旧操作 |

恢复方法验证lease.fd仍持有、safe为真、项目身份一致；只删当前state没有job关联的op-*。
job预留（含异常op样式job ID的防御情况）、已有artifact、cursor和其他state不删除。
旧owner死亡只是条件之一，必须通过ProjectLock的旧进程域核验；损坏/creating记录保守阻断。
删除与新预留/接纳同事务，任一失败均回滚，下次再试，不虚报已释放。

不从owner记录自动打开旧state：跨state共用项目锁，但只恢复调用方绑定的数据库。
owner尚活或进程域未清时，PROJECT_BUSY/CLEANUP_FAILED优先阻断；这条恢复分支不承诺
与旧版本先报STATE_LIMIT的竞争优先级相同。正常无op-*路径保持原有错误优先级。

## 测试方法

证据目录：`audits/cq-mcp-op-recovery-20261026-01/`。before/和before-manifest.json
保留本轮修改前4份产品源码及4份规格/用户文档；文档旧字节与前轮证据摘要核对一致。
之前的控制审核包、报告及证据清单均不覆盖。

先添加13项定向测试，再改产品：修复前10失败/3通过；修复后13项全部通过。
负控证明旧op预留确实阻止27MiB夹具接纳新9MiB，而非测试只检查新增字段。
随后补12项真实stdio崩溃与5项不确定owner/跨state边界，合计30项新增测试。

真实stdio矩阵为gate/diff × reserved/active/snapshot × quality/scan恢复触发，共12项/平台：

- reserved：在预留事务COMMIT之后设置测试屏障，尚未启动core；独立第二服务尝试不能抢预留。
- active：通过真实进程域启动受控父/子进程树，替代本次core子命令以保证精确活动窗口。
- snapshot：实际gate/diff核心已执行，artifact已提交，返回前设置屏障；提交的快照仍可读回同摘要。
- 只强杀stdio服务owner，不主动杀整树；恢复始终走未修改的`-m ai_code_quality.mcp`入口。
- Linux验证SIGKILL后父/子仍存活，quality和scan均CLEANUP_FAILED且预留不动；控制器确认出生身份，
  只清本夹具进程组后重试成功。Windows验证Job Object已回收父/子后才恢复。
- 重连initialize/artifact_get不抢清理，执行触发后预留归零；旧run字节、旧artifact和已提交快照不变。

这些是测试边界插桩加真实owner强杀、真实协议与真实恢复入口，不冒称完全黑盒随机强杀。
只有active替换core命令，reserved/snapshot执行真实gate/diff；恢复scan使用真实ruff-check。
SQLite故障回滚为显式注入，不能称物理满盘；实际ENOSPC另由原有Linux磁盘测试验证。
27MiB是逻辑配额夹具，16MiB控制余量保持原值，未填充Windows物理磁盘。

## 执行结果

| 运行 | 结果 | 耗时/范围 |
|---|---|---|
| Windows全回归 | 440 passed，0 fail/error/skip | 115.095s；排除单独分批capacity/POSIX/物理满盘模块 |
| Linux故障恢复 | 93 passed，0 fail/error/skip | 64.863s；30 op恢复+20控制+31存储+6旧stdio崩溃+2实际ENOSPC+4POSIX |
| Windows早期stdio定向 | 12 passed | 41.170s；已被最终440项覆盖，不相加成独立测试数 |
| Linux早期定向 | 25 passed | 30.143s；早于5项不确定owner/跨state补验，最终93项包含全部 |
| Linux证据补跑 | 14 passed，无skip | 34.475s；产品未变，12 stdio+2真实ENOSPC，在同一WSL调用结束前归档 |
| 配额竞争/控制子集 | Windows3、Linux3 passed，无skip | 1.181/0.830s；连接/八进程竞争、耗尽时实际进程取消与读取；各3项长压力未重跑 |
| 静态 | 全通过 | ruff/check/format、mypy、git diff --check、正式.cq与HEAD一致；实际输出见static-checks.json |

真实stdio共两平台24个场景，进程PID/出生身份、旧预留字节、屏障、恢复前后记录和
stderr保留在process-proofs/；Windows取最终回归，Linux取同源码证据补跑。ENOSPC控制器记录另外保留。
collect_results.py从实际XML/JSON提取计数并验证清单，不根据shell包装器exit0推断通过。
JUnit record_property/xunit2提示、WSL代理提示原样保留；本批没有联网调用。

归档失败轮：首次复制Linux过程文件时/tmp下的测试目录已不存在，原93项JUnit/日志仍在。
诊断显示/tmp为tmpfs且WSL刚重启。没有伪造文件或改写原XML，追加独立14项证据补跑，
改用/var/tmp并由run_linux_proofs.py在同一WSL调用内复制文件。collection-failure.json保留说明。
这14项与93项重复，不能相加为独立测试数；产品和测试源码均未因归档问题修改。

自扫：`cq-mcp-op-recovery-selfscan-20261026-01`，7工具ok，import-linter无配置skipped，
scan_consistency=consistent；覆盖率4037/4803=84.05163439516969%。自扫默认12 skip
（6容量/4POSIX/2实际满盘），不是通过项；相关故障/容量子集在上述独立批次显式执行。
原有SQLite连接ResourceWarning仍保留，未声称警告清零或已完成连接分配栈归因。

相对`cq-mcp-control-followup-selfscan-20261026-01`新增0、修复0、仍存在7、豁免1，diff exit0。
这里的“修复0”是静态规则finding差异，预留恢复功能由新增30项运行测试验证。
A门仍exit1，既有blocker1/high1，new_blocker_high通过；没有调整阈值或豁免换绿门。
本轮只关闭GLM F3定向修复，完整T07/T19/发布矩阵不关闭；修订候选未再次独立签署。

## 范围

本轮处理GLM F3，不改变质量规则、阈值、豁免和正式.cq；未安装依赖、未commit/push/发布。
检测来自底层ruff/mypy/radon/vulture/pytest/import-linter/DeepSec，cq负责编排与聚合。
完整宿主大结果/长调用/断开全链、Windows真实满卷、全部混合故障和发布许可检查仍按原任务表待验。
