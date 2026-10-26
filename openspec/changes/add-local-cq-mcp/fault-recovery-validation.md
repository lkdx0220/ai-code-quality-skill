# stdio 崩溃、SQLite 与磁盘故障验收

日期：2026-10-26。基线 HEAD：`32849e114c9ae7ee96bf86e2a6b90c86f7a95ebc`。
这是故障测试批次及作者验证记录，不是独立审核、全矩阵通过或发布批准。

## 结论与未关闭项

真实 stdio owner 强杀、SQLite 事务回滚、原子文件写入失败和 Linux 实际 ENOSPC
均已执行。发现并修复一项错误映射缺陷：`Store.transaction` 原先在 try 外建立连接，
连接失败会逃出结构化处理；现在连接建立也在 try 内，返回 `IO_ERROR`，并只对已建立的
连接执行回滚/关闭。没有改变事务、配额、锁、正式 `.cq` 或质量阈值。

**仍有两项规格差距，不能据本报告关闭 T07 或全部故障验收：**

1. design §5 的 job_get/cancel 受理 `<1s` 不适用于本轮真实 SQLite 写锁竞争。
   实测 job_get 约 10s 才返回 `STATE_BUSY`：业务事务等待 5s，随后服务审计再等待 5s。
   本轮没有修改超时或审计策略；下一批需明确并实现故障时的控制通道期限。
2. design §8 要求物理磁盘满时仍优先回收子树。当前 state 实际耗尽时，cancel
   因无法持久化标记返回 `IO_ERROR`，子树仍存活；释放空间后重试才取消并确认清理。
   本轮验证了真实失败行为与恢复，**没有证明该要求已实现**。16MiB 逻辑控制余量
   不是操作系统级保留空间，也不能承诺物理 ENOSPC 下取消可用。

下一批修复应分别覆盖有界的数据库/审计失败路径，以及本服务持有任务在持久化失败时的
取消信号与进程回收；须保留“已发出取消 / 已确认清理 / 终态已持久化”的事实区别。
本轮未用放宽规格或调整测试阈值来将这些差距记为通过。

## 本轮结果

| 运行 | 结果 | 时间 | 范围 |
|---|---|---|---|
| Windows 故障定向 r02 | 31 passed，0 skip | 34.90s | 5 stdio 崩溃 + 26 存储故障 |
| Linux 故障定向 r04 | 31 passed，0 skip | 29.66s | 相同 31 项，含实际进程组残留阻断 |
| Linux 实际磁盘满 r03 | 2 passed，0 skip | 7.83s | state / project 两个独立 32MiB tmpfs |
| Windows 回归 r02 | 384 passed，0 skip | 72.39s | 除显式分批压力/Linux/磁盘模块外的回归，包含上述 31 项 |
| 静态检查 | 全部通过 | — | ruff check；ruff format --check：82 文件；mypy：44 源文件 |

三个故障定向运行合计 64 次用例执行，涉及 33 个参数化场景；不是 64 个不同测试，
也不是每场景稳定性重复 6 次。384 项回归包含 Windows 的 31 项，不能再相加计数。
JUnit 的 record_property 在 xunit2 下产生兼容性警告，但属性实际保留于 XML；汇总逐项读取。

Windows 回归明确排除 `test_capacity_stress.py`、`test_posix_recovery.py`、
`test_disk_full.py`。压力与 POSIX 恢复已有各自验收记录；实际磁盘满在本批 Linux
单独显式启用。没有将这些模块默认 skip 充作通过。

## 真实 stdio owner 崩溃

新增 `tests/mcp/test_stdio_crash.py` 与测试专用 bootstrap
`tests/mcp/fixtures/fault_stdio_server.py`。真实 SDK `stdio_client` / `ClientSession`
握手并核对九工具、text/structuredContent 等价和 isError 与 envelope 一致。

| 窗口 | 注入方式 | 恢复断言 |
|---|---|---|
| precommit | jobs 已插入，事务尚未提交，测试屏障暂停 | 强杀后事务回滚，无 job/预留残留 |
| accepted | 接纳已提交，worker 尚未 spawn，测试屏障暂停 | 旧 job 为 interrupted；同 key 返回原终态，不重放 |
| active | 真实受控子进程和孙进程均存活 | Windows Job Object 回收；Linux 残留阻断新任务 |
| published | 核心发布 marker 已写，job 终态未提交 | 重启 job 为 interrupted，已发布证据仍 verified 且可读取 |
| blackbox | 无测试 patch 的 `python -m ai_code_quality.mcp`，真实 doctor | 真实服务断连，普通入口重连恢复；按重连时实际存活情况核对残留 |

控制器只杀 owner PID，不杀整棵树；Windows 使用 TerminateProcess，Linux 使用 SIGKILL。
四个精确窗口是测试进程内 patch 的屏障/受控命令，不是发布入口新增的故障开关；恢复均走
未修改的 stdio 服务。published 的核心扫描使用安静 adapter，验证真实发布流程，
不代表该夹具实际执行了 ruff 或完整分析工具链。blackbox 使用真实 doctor。

Linux 的受控 active 窗口保证子树残留，新任务得到 `CLEANUP_FAILED`；控制器核对出生身份后
显式清理该进程组，随后恢复成功。不能把控制器清理说成产品自动回收。真实 doctor
可能在重连前自然结束，因此黑盒案例不要求每次都留下孤儿。全部已提交旧任务均不重放，
清理确认后预留归零，新 key 可接纳。

## SQLite 和原子写入故障

新增 `test_storage_faults.py` 和独立 SQLite 写入进程夹具 `sqlite_fault_owner.py`。

- 接纳阶段 connect、insert 后、commit 前失败共 3 项；返回结构化错误，无半个任务、
  半笔预留或泄漏的项目执行锁，恢复后同 key 可重新接纳。
- 快照 insert / commit 失败共 2 项；旧快照与旧预留保持不变，恢复后可以保存/结算。
- 终态更新写入后失败 1 项；状态和预留一起回滚，不能只释放预留却不更新状态。
  这只验证事务原子性与显式重试，不证明 worker 终态持久化失败能在原进程自动愈合。
- 独立 OS 进程持有实际 SQLite 写锁，另一个请求等待后返回 `STATE_BUSY`，审计失败有 warning；
  另以真实未提交 insert 后强杀写入者，核对 SQLite 自身恢复、integrity_check 及台账无变化。
- write / flush / fsync / replace × ENOSPC / EACCES / EIO 共 12 项：在真实临时文件已写入
  部分内容后注入异常，旧目标字节不变，临时文件被移除。
- `.complete.json` 的 fsync / replace × 三种 errno 共 6 项：不发布新 marker，
  未完成 run 不能作为已发布证据消费。

后两类是确定性函数边界注入，不冒称真实设备权限故障或物理 I/O 损坏。

## 实际 ENOSPC

`test_disk_full.py` 显式要求 `CQ_MCP_REAL_DISK_FULL=1`，只在隔离、具有挂载能力的 Linux
验收环境运行。控制器执行 `unshare --mount --propagation private`，在唯一
`/var/tmp/cq-disk-full-<UUID>/volume` 内挂载上限 32MiB 的 tmpfs。
循环实际写入直到 OS 返回 errno 28，statvfs 的 available_bytes 为 0。
没有填充主机硬盘。屏障、stderr 与结果记录在该文件系统之外，退出时卸载。

1. **state 耗尽**：先创建已知旧 job/快照，再启动真实子树。满盘时旧结果仍可读；
   cancel 返回明确 `IO_ERROR`，持久化 cancellation_requested 仍为 false，子树存活。
   删除填充文件后重试取消成功，最终 cancelled / cleanup=confirmed，父子进程退出、
   预留归零，旧证据不变。这是已知差距的负向验收，不能写成“满盘取消成功”。
2. **project/audits 耗尽**：state 在另一个可写文件系统。已有发布 run 先固化摘要，
   等盘满再释放受控真实核心 scan。核心 exit4，job failed / IO_ERROR / cleanup=confirmed，
   新 run 无 marker，旧 run 全文件摘要不变且 findings 可读，预留归零。

两项最终均卸载成功。它们验证 tmpfs 实际空间耗尽，不等价于块设备缓存、断电、
目录 fsync 或 Windows 物理卷写满。

## 证据与复现

证据根：`audits/cq-mcp-faults-20261026-01/`（被 Git 忽略，不随代码提交）。

- `windows-faults-r02.xml/.log`、`linux-faults-r04.xml/.log`：最终 31 项定向记录。
- `linux-disk-r03.xml/.log`：两项实际 ENOSPC，属性含 errno、剩余空间、响应、清理和卸载事实。
- `windows-regression-r02.xml/.log`：384 项最终回归；XML 保留故障场景属性。
- `linux-fixtures/`：从 Linux 唯一目录复制的小型屏障、stderr、seed/result 记录；
  不把卸载后的空目录描述为保留了 tmpfs 内原始文件。
- `results.json` / `collect_results.py`：从每轮 JUnit 重建逐用例结果、属性、耗时及失败计数。
- `evidence-manifest.json`：本批产品修复、测试/夹具、报告/文档、日志与结果的字节数及 SHA256。

Windows 最终回归使用已有 runtime-venv 的 Python3.13.14（自带 MCP2.3.0/pywin32），
PYTHONPATH 为本仓 src 加已有全局 Python3.13 site-packages，借用 pytest/工具链。
basetemp 使用 Git 仓库外唯一临时目录，server 指向该 runtime；没有新安装依赖。
Linux 为 WSL Ubuntu，已有 `/root/cq-mcp-linux-tests-20261025-01/bin/python`（3.11.16）。

定向复现（需上述已有依赖；源码导入路径和服务解释器按环境设置）：

```text
python -m pytest tests/mcp/test_stdio_crash.py tests/mcp/test_storage_faults.py -v
CQ_MCP_REAL_DISK_FULL=1 python -m pytest tests/mcp/test_disk_full.py -v -s
```

第二条是 Linux 环境变量写法，必须在私有挂载可用的隔离验收环境执行。
这不是全新安装测试，也不是 Kimi/ZCode/Claude 真实宿主断开验收。

## 失败轮保留

- Windows storage r01：25 passed / 1 failed，暴露 connect 在 try 外的产品缺陷；修复后通过。
- Linux faults r01：30 passed / 1 failed，黑盒测试错误地要求 doctor 必须存活到重连；
  改为按实际存活情况检查，受控 active 仍严格要求残留与阻断，未放宽产品断言。
- Linux faults r02：32 passed / 1 failed；state 满盘行为已验证，但测试夹具未关闭 SQLite
  连接导致卸载失败。改用 closing 后，disk r03 两项卸载成功；未改产品逻辑。
- Windows regression r01：381 passed / 3 failed；父 pytest 的临时 addsitedir 未传给子进程，
  两项子进程缺 MCP/pywin32；basetemp 在真实仓库 audits 内，使空夹具的 Git 查询落入父仓
  而污染 spec-gate 预期。改用已有 runtime 解释器和仓库外 basetemp 后 384 passed，
  未弱化 spec-gate 或测试断言。首轮错误日志仍保留。

## 范围边界

未承诺所有存储失败排列、物理断电、目录落盘持久性、Windows 实际满卷、Windows 只读 ACL、
任意 PID 重用排列，或 worker 终态持久化失败的自动修复。真实宿主大结果/长调用/断开全链、
依赖许可证和最终发布检查仍按 tasks 保留。历史正式 A 门仍红，本批没有重跑完整自扫/A 门，
不能从 lint/类型/回归通过推出 A 门通过；既有 findings 和正式 `.cq` 未改。
未 commit、push、发布或调用外部模型。
