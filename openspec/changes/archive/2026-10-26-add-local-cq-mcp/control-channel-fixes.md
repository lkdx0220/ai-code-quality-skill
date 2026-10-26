# 控制通道故障修复与复验

日期：2026-10-26（Asia/Shanghai）。基线 HEAD：`32849e114c9ae7ee96bf86e2a6b90c86f7a95ebc`。
这是作者修复候选与执行证据，不是独立审核、全规格通过或发布批准。

## 结论

根因报告的四条链路均已修复并通过对应测试：查询/审计不再串行等待两次SQLite写锁；
本owner任务的取消信号不再依赖写库成功；跨实例轮询不阻塞期限检查；终态写入失败后
保留内存事实，并在恢复空间后由查询/下一次接纳/正常关闭触发原子补记与预留结算。

Windows回归398项通过；Linux故障/恢复51项通过。Linux真实32MiB tmpfs空间耗尽时，
不释放空间即完成受控子树回收，返回内存终态与未持久化标记；恢复空间后无需控制器
直接改库就能结算。独立进程持有RESERVED/EXCLUSIVE锁时，查询/取消受理均<1s。

没有放宽design §5的<1s要求，没有把16MiB逻辑余量解释为物理保留空间。
未改正式`.cq`、评级算法、阈值或豁免。自扫新增问题0，A门仍红。

## 实现

| 故障链 | 变化 | 返回事实/边界 |
|---|---|---|
| SELECT也执行BEGIN IMMEDIATE | 控制读取使用SQLite只读URI连接和BEGIN；控制读写busy预算100ms，其他普通写事务保留原预算 | RESERVED下读取成功；EXCLUSIVE下明确STATE_BUSY，不再追加5s审计 |
| JSONL审计使用数据库写锁 | 独立calls.lock；同进程线程互斥加跨进程OS锁，竞争预算50ms；失败warning | 不丢弃业务错误，也不假称审计成功；高竞争可明确降级，不保证任意负载无丢审计 |
| cancel只写数据库标记 | 新control.py按job_id登记本owner事件；先发内存信号再尝试落盘；任务互斥串行化本地取消和终态选择 | 已选定终态不追改；接受取消不等于清理完成；其他实例仍依赖持久化标记，不按外部PID直接发信号 |
| 每30ms的轮询可等库5s | 轮询使用只读连接、零busy等待；存储忙/不可用让出循环，保留内存取消/期限检查；spawn前再查取消 | 总期限检查前后包围回调；故障回调不再按5s busy超时阻断 |
| finish失败后丢弃worker结果 | 脱敏pending终态留在本owner；查询/新执行前/正常关闭重试finish事务 | cleanup事实与state_persisted分离；终态与预留仍原子提交，失败不会单独释放数据库预留 |

busy/锁预算不是操作系统硬实时保证；线程调度、文件系统调用本身被OS挂起等不由SQLite
busy_timeout控制。下表保留端到端实际耗时，不把配置100ms冒称所有调用均100ms返回。

`state_persisted=false`、`state_source=owner_memory`、`persistence_error`和warning明确标注
本进程观察结果；`cancellation_persisted`单独表示取消标记是否已写入。恢复写入后，
返回`state_source=state_store`、`state_persisted=true`。查询旧owner恢复interrupted也带这些字段。
工具描述、docs/mcp.md、design和增量spec已同步。上一批连接异常映射修复仍保留，
不将它重新计为本轮发现。

## 定向结果

| 场景 | Windows | Linux |
|---|---|---|
| 独立RESERVED锁下读取已知终态job | 5.73ms，成功 | 2.45ms，成功 |
| 独立EXCLUSIVE锁下读取已知终态job | 447.36ms，STATE_BUSY | 101.99ms，STATE_BUSY |
| 同锁下参数类型已错误的job_get | 2.78ms，INVALID_ARGUMENT | 0.35ms，INVALID_ARGUMENT |
| 本owner运行子树、RESERVED锁下cancel | 183.17ms，内存接纳/落盘失败 | 102.35ms，同左 |
| 本owner运行子树、EXCLUSIVE锁下cancel | 439.79ms，内存接纳/落盘失败 | 101.86ms，同左 |
| state实际ENOSPC下cancel | 未填充Windows物理卷 | 两轮约1.87/1.67ms接纳；满盘期间已cancelled/cleanup=confirmed/state_persisted=false |

计时取Windows398项回归、Linux51项故障和Linux最终补验的JUnit属性，不是平均值或性能排名。
每个锁场景均断言受理<1s；旧诊断中的查询10.019s见control-channel-root-cause.md。

还覆盖了：跨实例写入可用时取消被owner轮询接收，不可写时<1s结构化失败；
EXCLUSIVE锁下0.2s执行循环期限仍能回收进程并返回timed_out；spawn前取消不启动命令；
取消先到/终态先到以及真实两线程同时完成/取消的状态一致性；终态写失败后下一次提交触发补记。

真实stdio新增pending崩溃窗口：核心已发布、子树已清理、Store.finish边界确定性注入IO_ERROR，
查询显示completed但state_persisted=false；仅强杀服务owner后，通过普通未修改服务入口重连，
恢复为interrupted、保留已发布证据、同key不重放、预留归零。这是注入终态写失败加真实服务强杀，
不冒称物理磁盘满与服务强杀同时执行。物理满盘回收另走真实tmpfs/stdio场景。

## 运行清单

证据根：`audits/cq-mcp-control-fixes-20261026-01/`（Git忽略）。

| 运行记录 | 结果 | 时间/说明 |
|---|---|---|
| windows-regression-r01 | 398 passed，0 skip | 67.918s；排除单独分批压力/POSIX/磁盘模块 |
| linux-faults-r02 | 51 passed，0 skip | 29.317s；13控制+26存储+6stdio崩溃+2实际满盘+4POSIX恢复/只读 |
| windows-followup-r01 | 7 passed，0 skip | 4.822s；配额竞争/控制3项+pending与终态相关4项；补验最终字段 |
| linux-followup-r01 | 10 passed，0 skip | 9.891s；相同7项+同时完成/取消1项+实际满盘2项；补验最终字段 |
| windows-repeat-01至06 | 每轮4 passed | 并发审计、同时完成/取消、两种写锁查询；6轮均通过，合计24次执行 |
| 两平台audit_crossprocess.py | 各1组断言通过 | 父进程持审计锁，独立子进程约54.2/51.3ms明确降级；释放后可写、JSONL完整 |
| 静态检查 | 全部通过 | ruff check；format84文件；mypy45源文件；git diff --check；正式.cq无diff |

这些运行重复覆盖场景，不能相加成独立测试数量，6轮也不是整个MCP矩阵各重复6遍。
398项回归在最终补上恢复元数据/工具说明前执行；最终产品又经过完整自扫中的pytest及两平台
上述补验。自扫pytest默认跳过压力/POSIX/实际满盘12项；这些不是自扫通过项，相关受影响子集
已经在显式启用的分批运行中执行。未重新运行1000任务/10000游标/100次最大快照的完整长压力，
上一批证据仍保留，本轮复跑预留竞争和配额耗尽控制三项。

JUnit的record_property/xunit2兼容提示仍保留，属性确实写入XML并由collect_results.py读取。
自扫pytest另有unclosed SQLite连接ResourceWarning；本批没有做分配栈归因，也不宣称警告清零。

## 自扫与质量门

使用已有runtime解释器，通过PYTHONPATH复用全局工具；DeepSec使用已存在的全局解释器。
doctor首轮因用runtime探测DeepSec得到optional缺失，保留doctor.json；显式选择既有DeepSec
解释器后doctor-r02.json exit0，八工具均可用。没有安装依赖或更改机器配置。

自扫run：`audits/cq-mcp-control-selfscan-20261026-01/`。7工具ok，import-linter因项目无契约
配置skipped，不能算架构检查通过；输入一致性consistent。检测能力来自
ruff/mypy/radon/vulture/pytest-cov/import-linter/DeepSec，cq负责编排、证据与门禁聚合。

- 相对`cq-mcp-service-20261025-03`：新增0、修复0、仍存在7、豁免1，diff exit0。
- 覆盖率：3985/4756 = 83.78889823380993%，超过原80%阈值。
- A门exit1：仍有既有blocker1/high1，new_blocker_high通过；没有新增blocker/high。
- 未为绿门修改`.cq`或放宽质量阈值；这批故障修复通过不等于A门通过。

## 失败轮保留

windows-targeted-r01为73 passed/1 failed：原并发审计完整性测试失败。
初版独立OS锁仅用5ms轮询，在同进程快速连续写入时竞争/饥饿；后续诊断观察到等待逼近50ms预算，
没有把它改成“允许少写几行”。增加按state路径共享的线程互斥，再由独立OS锁处理跨进程；
windows-targeted-r02为79 passed，后续398项与六轮重复均通过。
这里不声称已经逐个追溯初轮所有false返回的底层errno；原日志、定向探针均保留。

linux-targeted-r01为14 passed，是较早的控制与实际满盘子集，不重复计入最终51项。
所有XML/log、repeat-results.json、两个audit跨进程记录、selfscan/diff/gate及static-checks.json
均保留。collect_results.py从JUnit重建results.json；linux-fixtures保留实际满盘控制器小型记录，
不冒称卸载后仍保留tmpfs内容。source-snapshot与evidence-manifest.json记录原字节、体积和摘要。

## 剩余边界

本owner内存pending不是第二份持久化数据库。另一实例看不到内存事实；服务退出且无法落盘时，
重启只能在进程域核对后保守interrupted。物理满盘时跨实例无法写标记仍明确失败。
这些边界已纳入规格与返回信息，不伪造取消、精确终态或持久化成功。

Windows实际满卷、OS文件系统调用无限挂起、物理断电、所有混合故障排列、任意负载下无饥饿、
真实Kimi/ZCode/Claude宿主的大结果/长调用/断开故障全链及最终打包/许可证仍未全部验收。
因此只关闭任务表中两条已复现故障的定向修复项，完整T07/发布矩阵保持待验。
未调用外部模型，未commit、push或发布；上一轮根因证据保持原样。
