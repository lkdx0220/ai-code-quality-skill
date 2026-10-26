# 控制通道独立审核意见处理与复验

记录日期：2026-10-26（Asia/Shanghai）。基线 HEAD：`32849e114c9ae7ee96bf86e2a6b90c86f7a95ebc`。
这是作者对用户转交的 Kimi / GLM 审核的后续处理，不是修订候选再次获得独立签署。

## 审核材料核验

原报告、初判、冻结包及两位审核者目录保持原样，本会话没有调用外部模型。
两份报告均完整读取。Kimi 整文件为17131字节，SHA256与用户提供值一致；
GLM整文件14404字节，按其“去掉末尾自引用两行”约定复算的SHA256与声明一致。
GLM整文件摘要与该约定摘要不同，不混用。完整摘要保存在本轮 results.json。

两位均为附条件通过；Kimi确认的事务回滚二次失败为基线已有问题，GLM的两个
控制通道边界问题为本轮新引入。不能将“可以进入下一验收”理解为全规格验收或发布批准。

## 处理决定

| 审核项 | 处理 | 实现与验证 |
|---|---|---|
| Kimi F-01，主失败被ROLLBACK二次错误替换 | 修复，并覆盖close二次失败 | 事务只映射原OperationalError，保护rollback/close；原ServiceError/KeyboardInterrupt保持原义。主操作无错误但close失败返回IO_ERROR，不假称成功 |
| GLM F1，pending提交后追加读取失败误报未落盘 | 修复 | _flush返回提交事实；get直接使用finish的已提交快照。Service级注入后续读故障仍state_persisted=true、无错误warning、预留已归零 |
| GLM F2，queued→running短暂竞争使整题failed | 修复 | 仅STATE_BUSY重试2s、受总期限限制；先成功写running再spawn。轮次间用事件等待；取消/期限先到不spawn，IO_ERROR立即失败；等待从执行预算扣除 |
| GLM F3，op-*预留在owner崩溃后滞留 | 确认代码缺少对应恢复，登记后续批次 | 本轮未修改quality.py及预留协议。不能根据年龄或PID消失直接删除：需先确认项目执行锁和原进程域已安全结束，补真实gate/diff强杀与容量负控后再修 |

F3可能每次滞留最多9MiB逻辑预留，反复崩溃可提前触发STATE_LIMIT；不是物理证据丢失，
也不能因此当作无影响。发布前须处理。其余P4记录保留原审核边界，没有冒称全部消除。
design/spec/docs及任务表已同步三项修复语义和待办。

## 复现方法与结果

本轮新路径：`audits/cq-mcp-control-followup-20261026-01/`。
原控制修复证据与冻结包未覆盖。before/保留修复前3份产品源码和2份测试源码及摘要。

先添加回归、再修改产品：首轮11项为9失败/2通过，原始before.log与before.xml保留。
9个失败分别覆盖4种主异常的二次清理、无主异常close、提交后再读、启动瞬时竞争、
启动中取消、启动中期限；恒定IO错误和持续竞争本来就会失败，负控原本通过。
随后11项全部通过；后续增加“等待扣减执行预算”第12项，并加强持续竞争为实际默认2s、
重试时job_get<1s断言，最终两平台运行见下表。

SQLite竞争由真实独立进程持BEGIN IMMEDIATE写锁产生，不是把整个worker替换成假结果。
成功路径启动真实Python子进程、写spawn标记、输出最小doctor JSON；检查锁释放前无spawn。
deadline用例直接缩短内部job预算至0.2s，测试worker机制，不冒称公共schema接受小数期限。
budget用例预算1s，锁等待约0.3s、子进程再等待0.85s，必须timed_out，不能在等待后重置1s。
rollback/close及不可用读通过Connection子类/Store边界定向注入，不冒称物理硬件故障。

| 执行 | 结果 | 边界 |
|---|---|---|
| Windows全回归 | 410 passed，无skip | 排除另行分批的capacity/POSIX/物理满盘模块；12项新增回归全部在内 |
| Linux故障/恢复 | 63 passed，无skip | 控制20+存储31+stdio崩溃6+实际ENOSPC2+POSIX恢复4 |
| Linux启动最终补验 | 5 passed，无skip | 持续竞争改为实际默认2s及新增等待中job_get断言之后执行 |
| 静态检查 | ruff/check/format、mypy、git diff --check通过 | 84格式文件、45源文件；.cq与HEAD一致 |

Windows全回归和Linux63项在最后加强测试断言前执行，产品代码此后未变。
最终Windows完整自扫再执行全部普通回归；Linux最终5项覆盖加强的测试。
上述运行重复覆盖场景，不能相加为独立测试数。record_property/xunit2提示保留，XML属性可读取。

## 最终自扫与质量门

最终run：`cq-mcp-control-followup-selfscan-20261026-01`。7工具ok，import-linter无配置skipped，
scan_consistency=consistent；覆盖率4022/4792=83.93155258764608%。
相对`cq-mcp-control-selfscan-20261026-01`新增0、修复0、仍存在7、豁免1，diff exit0。
A门仍exit1：既有blocker1/high1，new_blocker_high通过，没有为换绿门改登记。
这里的“修复0”指底层静态规则finding差异，三项功能缺陷由新增运行回归验证。

自扫默认跳过6容量/4POSIX/2实际满盘，共12项，不能把skip记通过；Linux相应故障子集
已显式运行，本轮容量长压力未重跑。最终Windows自扫已包含最后加强的启动测试。
原有SQLite连接ResourceWarning仍出现，日志原样保留；没有声称连接警告清零或完成分配栈归因。
结果、覆盖率、diff/gate及证据清单由collect_results.py从实际XML/JSON提取并校验摘要。
检测能力来自ruff/mypy/radon/vulture/pytest/import-linter/DeepSec，cq负责编排与聚合。
未安装依赖、未改.cq/阈值/豁免、未commit/push/发布。

## 未完成边界

本轮只关闭三项审核后续修复。GLM F3仍待专门施工；未重新执行全部1000任务/万游标/
百次大快照长压力，也未执行Windows真实满卷、真实宿主大结果/长调用/断开全链。
这些已有边界和完整T07/T19/发布矩阵仍保持待验；不以本次定向通过替代。
