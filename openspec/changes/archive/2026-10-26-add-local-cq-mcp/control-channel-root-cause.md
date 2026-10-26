# 控制通道故障根因排查

日期：2026-10-26。基线 HEAD：`32849e114c9ae7ee96bf86e2a6b90c86f7a95ebc`。
本轮按“先排查原因”执行，只增加诊断脚本、证据和本文，不修改产品代码、规格要求或测试阈值。
上一批 `Store.transaction` 的连接异常映射修复仍保留，不能将它记为本轮修复。

## 判断

共同根因是控制路径没有从存储故障中隔离：读取也抢 SQLite 写锁，审计在返回前再抢同一把锁；
取消依赖数据库更新成功，worker 的内存取消事件没有接到 job_cancel。
进程回收机制在本轮 Linux 满盘场景可以工作，取消信号没有送达才是第一处故障。

另外确认两项相关缺口：worker 的数据库轮询能阻塞期限检查；子树已清理但终态写入失败时，
当前进程没有自动补记机制，查询仍可显示 running，并保留该任务的容量预留。
这两项应与原先两个验收缺口一起纳入后续修复范围。

## 1. 查询约 10 秒：读请求被当作写事务，失败审计又串行等待

调用链：

```text
Service.call(cq_job_get)
  → Store.job
    → transaction: BEGIN IMMEDIATE → 等写锁约 5s → STATE_BUSY
  → 组装错误结果
  → await Store.audit
    → transaction: BEGIN IMMEDIATE → 再等约 5s → 审计失败 warning
  → 返回结果
```

`store.py:66` 的通用事务固定使用 `busy_timeout=5000` 和 `BEGIN IMMEDIATE`。
`job`（134）、`read_artifact`（233）、`read_cursor`（266）等只读方法也复用它，
所以本来只需 SELECT 的操作也请求写锁。`audit`（277）虽写的是 JSONL，仍为跨实例轮转
持有同一个数据库事务。`service.py:70` 在返回前 await 审计，形成两段串行等待。
`asyncio.to_thread` 使这些操作不直接阻塞事件循环，但不会消除单个响应的等待。

独立 OS 进程持有真实 `BEGIN IMMEDIATE` 时，本轮测得：

| 探针 | 结果 |
|---|---|
| 同数据库、独立连接的普通 SELECT | 成功，0.237ms |
| 产品 Store.job 阶段 | 5.0081s 后失败 |
| 随后的 Store.audit 阶段 | 5.0084s 后失败 |
| Service.call 完整返回 | 10.0193s，STATE_BUSY，含审计 warning |
| 参数本身已非法、不经过业务读库的调用 | 仍被审计拖到 5.0100s 才返回 INVALID_ARGUMENT |

失败 SQL 均为 `BEGIN IMMEDIATE`，原生错误码 5 / `SQLITE_BUSY`。
普通 SELECT 的对照只证明本轮 RESERVED 写锁下无需阻塞，不能推出独占锁、热日志恢复或
存储损坏时任意读取均可用。线程池压力、并发放大和所有锁状态没有在本轮定量验证。

## 2. 满盘不能取消：持久化标记是唯一的 job_cancel 信号路径

`service.py:127` 的 job_cancel 只调用 `Store.cancel`。
后者在 `store.py:158` 读取 job、把 cancellation_requested 改为 true，再执行 UPDATE。
失败则事务回滚、返回 IO_ERROR；没有后备动作去触发 worker 的取消事件。

`Service._accept_and_start` 为每个 worker 创建了 threading.Event，但仅放入一个无 job_id
索引的 set。正常 job_cancel 没有按 job_id 找到并设置它；shutdown 才会设置全部事件。
`jobs.py:120` 让进程循环通过读库轮询 cancellation_requested。
因此存在以下链路：

```text
物理空间耗尽 → 取消 UPDATE 失败 → 标记仍为 false
                              → worker 内存事件也未设置
                              → 轮询继续读到 false → 子树继续运行
```

本轮在私有挂载命名空间内使用 32MiB tmpfs，实际写入 33,497,088 字节填充数据，
OS 返回 errno 28，available_bytes=0。服务使用真实受控子进程与孙进程，不运行分析器。

| 步骤 | 实测 |
|---|---|
| 正常调用 job_cancel | IO_ERROR；worker event=false；持久化标记=false；父子进程仍存活 |
| SQLite 出错语句 | UPDATE jobs SET body=? WHERE id=?；错误码 13 / SQLITE_FULL |
| 不释放空间，诊断脚本直接设置 worker 已有事件 | 27.4ms 内完成执行线程退出/回收路径；进程组无存活成员；lease.safe=true |
| 此时 tmpfs 剩余空间 | 仍为 0 |

直接设事件是**探针控制器的因果对照**，不是当前产品 job_cancel 的能力，也不是已经修复。
它说明在这个场景下底层进程组回收并不要求 state 可写；阻断点在取消信号送达之前。
不能把 27.4ms 推广为 Windows 或任意系统负载下的回收 SLA。

16MiB `CONTROL_HEADROOM`（store.py:18、90）只在服务逻辑容量准入中保留余额，
没有操作系统预分配或磁盘保留空间。外部文件、其他进程或共享文件系统仍可耗尽物理空间；
增大逻辑余额本身不能闭合取消保证。

## 3. 期限检查也被数据库轮询挡住

`processes.py:231` 先执行 `cancel.is_set() or cancelled()`，234 才检查总期限。
worker 的 cancelled 回调是上述 Store.job，仍可能在写锁上等待 5s。

本轮直接调用真实 execute 循环，将诊断期限设为 0.1s，并维持实际独立写锁：
5.0172s 后才以 STATE_BUSY 退出；finally 回收已确认，进程组无残留。
0.1s 是 execute 的定向探针参数，不宣称它是工具 schema 接受的扫描期限。

这证明一个阻塞轮询就能超过期限，并以数据库错误而非 timed_out 收尾。
本轮未测反复短暂锁竞争能将总时长延后多少，也未模拟线程池耗尽。

## 4. 清理成功与终态持久化没有恢复衔接

满盘下直接触发内存信号后，执行循环已经清理了子树，但 `jobs.py:142` 的 Store.finish
又在 `UPDATE jobs SET state=?,body=? WHERE id=?` 上遇到 SQLITE_FULL。
其 finally 仍释放项目执行锁；该 worker 已结束，终态事务与预留删除一起回滚。

释放填充文件后，本轮通过原来的 Service.call 查询，同一服务进程仍然存活：

- `cq_job_get` 成功，但返回 `state=running`、`cleanup=not_started`。
- worker task 数量为 0，实际子树已空、项目 lease 已释放。
- `reserved_bytes=9,437,184`（9MiB），没有自动结算。

原因是 `_job_get`（jobs.py:191）仅在 owner 进程死亡/出生身份变化时走 interrupted 恢复，
不会在 owner 仍活着但 worker 已结束时补记。没有持久化重试或进程内待结算结果可供查询。
控制器最后显式 Store.finish 才将预留归零，这一步不记为产品自动愈合。

这是本轮探针触发既有内存事件后复现的终态写入失败路径；正常退出/超时的其它触发方式
未逐一重跑，但它们共享同一个 finally。不能据此宣称所有触发方式均已动态验收。

## 后续修复必须覆盖的边界

1. 查询使用适合只读的访问路径；控制请求具有总时间预算。审计失败应有可见 warning，
   同时不能在业务已经失败后再无条件等待一个完整写库超时。仅调短统一 timeout 仍保留错误耦合。
2. 本进程拥有任务的取消应有按 job 身份定位的独立信号，并与完成/取消竞态、跨实例取消、
   queued-before-spawn、owner 身份核对一起设计；不得凭任意外部 PID 直接杀进程。
3. 期限检查不能依赖一次可能长时间阻塞的数据库轮询。不能只把两行顺序对调便承诺严格期限，
   因为进入回调之后仍可能阻塞。
4. 清理事实、终态持久化事实和容量结算分开记录并可恢复；数据库失败时不假称终态落盘，
   也不能让同一 owner 内已经退出的 worker 永久显示 running。

这是根因与修复约束，不是施工已完成。本轮不调整 design §5 的 <1s 或 §8 的满盘优先回收要求。

## 证据与范围

新证据目录：`audits/cq-mcp-control-diagnosis-20261026-01/`（Git 忽略）：

- `probe.py`：仅诊断使用，计时包装、SQLite Connection 子类记录实际失败，不改变 SQL/timeout。
- `lock-result.json`：独立锁进程、分段耗时、原生 SQLite 错误、期限路径。
- `disk-result.json`：ENOSPC、失败语句、事件状态、父子进程组、终态失败、卸载与控制器结算。
- `source-snapshot/`：本轮相关产品/夹具的原字节副本；`collect.py` 校验结果并生成证据清单。
- `evidence-manifest.json`：本文、探针、结果及关联产品源码的原字节摘要。

本轮两组探针各执行一次，断言均通过；不是稳定性重复测试，不替代上一批真实 stdio 故障验收。
本轮直接调用 Service，以便观测 worker 事件与 SQL 失败点；SQLite、独立锁进程、子树、
tmpfs ENOSPC 均为真实。上一批 stdio 客户端看到的同类现象见 fault-recovery-validation.md。
运行环境为 WSL Ubuntu、已有 Python3.11.16；没有安装新依赖。
WSL 仍输出已有 localhost 代理提示，本轮不联网，该提示不是上述锁或满盘失败的依据。
tmpfs 已卸载，诊断子树与写锁进程已退出。没有填充主机硬盘。

复现（Linux 私有挂载能力按上一批验收环境准备，源码 PYTHONPATH 指向本仓 src）：

```text
python audits/cq-mcp-control-diagnosis-20261026-01/probe.py lock
unshare --mount --propagation private python audits/cq-mcp-control-diagnosis-20261026-01/probe.py disk
```

结果同时写入 `/var/tmp/cq-control-diag-<UUID>/result.json`，控制器输出相同 JSON。
没有重跑全量回归/自扫/A 门，未 commit、push、发布，也未调用外部审核模型。
