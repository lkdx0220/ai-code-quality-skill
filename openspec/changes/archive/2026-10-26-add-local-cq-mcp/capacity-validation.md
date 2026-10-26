# 容量与配额验收

日期：2026-10-26。基线 HEAD `32849e114c9ae7ee96bf86e2a6b90c86f7a95ebc`。
本批只增加测试、验收记录和文档，不改产品代码、默认配额、正式 `.cq`、阈值或发布状态。

## 结果

Windows / CPython 3.13.14 与 WSL Ubuntu / CPython 3.11.16 各通过六项压力用例：
第一批五项全部通过，再单独补验八个独立进程的配额竞争一项。合计 12 项通过，
无失败、无 skip。这里的六项是测试场景数量，不是六次稳定性重复验收。

| 场景 | Windows | Linux | 判断依据 |
|---|---|---|---|
| 1000 个约 1 KiB 小结果任务 | 1000 接受，第 1001 个 STATE_LIMIT | 同左 | 所有任务和快照重开台账后逐项可读；无预留余额 |
| 10000 活动游标 | 第 10001 个 STATE_LIMIT | 同左 | 10000 个 token 全部重开读取；重复页复用；一个过期槽位可回收，其他 token 不变 |
| 100 次最大快照尝试 | 接受 29，拒绝 71 | 同左 | 每份 8 MiB；29 份逐项重读并核对摘要，无驱逐、覆盖或失败后容量增长 |
| 八连接并发预留，三轮 | 每轮 1 接受、7 STATE_LIMIT | 同左 | 独立 SQLite 连接共享配额；结算后预留归零 |
| 八个独立 OS 进程并发预留 | 1 接受、7 STATE_LIMIT | 同左 | 进程间同步起跑，赢家预留持续保留至全部退出，再由父进程释放 |
| 配额耗尽时的控制通道 | 查询/读取/取消成功 | 同左 | 新工作和新索引拒绝；实际运行子进程取消后退出，cleanup=confirmed |

小任务 state 物理大小均为 3,035,136 B；游标 state 分别为 1,478,656 / 1,474,560 B。
最大快照 state 两平台均为 243,576,832 B，低于 240 MiB 正常接纳池；剩余空间不足以
为下一次操作再预留 9 MiB，因此第 30 份拒绝符合契约。16 MiB 控制余量没有用于接纳新工作。

Windows 第一批五项 162.99s，独立进程补验 0.38s；Linux 分别 109.37s / 0.59s。
两平台部分并行执行，时间只是本次验收观测，不能用于操作系统性能排名。

## 方法与边界

新增 `tests/mcp/test_capacity_stress.py` 和 `tests/mcp/fixtures/capacity_reserver.py`。
测试使用真实 SQLite、事务、序列化、脱敏和项目锁，不直接向表里灌入 1000 个任务或
10000 个游标。为避免每次普通回归产生数百 MiB 测试数据，压力测试须显式设置
`CQ_MCP_CAPACITY_STRESS=1`；本次运行全部启用，未将默认跳过算作通过。

- 小任务直接执行真实 `_submit` 接纳和快照/`finish` 结算，受控结果约 1 KiB；
  **不是 1000 次真实 doctor/分析器子进程运行，也不是 1000 次 stdio 宿主调用**。
  第 1001 次拒绝、终态幂等重用、查询、取消终态任务及快照读取走实际 `Service.call`。
- 游标通过真实 `Store.cursor` 创建和去重；仅将一个 token 的过期时间设为 0，
  验证 TTL 判定与回收逻辑，不声称实际等待了 24 小时。
- 100 次快照尝试使用原始 8 MiB 文本和真实默认 256 MiB 容量，经 `Store` 执行
  9 MiB 事务预留、保存、释放及重读。不是 100 次 CLI 大 diff，也不是端到端捕获吞吐测试。
- 控制通道用 27 MiB 缩小容量夹具，保留真实 16 MiB 控制余量及 9 MiB 操作预留。
  先启动实际睡眠子进程，再通过计入物理配额的填充文件留下不足 64 KiB 接纳空间；
  没有改产品默认值。doctor、scan 和新列表索引均 STATE_LIMIT；已有列表游标最后一页、
  已有快照、job_get 与同 key 重用成功，取消后预留归零，锁可重新取得。
  Windows job_get / cancel 受理约 4.64 / 7.40 ms；Linux 约 0.74 / 4.76 ms。
  两平台均明确断言 <1s，且确认子进程已退出，不只检查 cancellation_requested。
- 八连接竞争覆盖三轮；另有真实八进程竞争一轮。没有将其表述为任意负载下的无饥饿保证。

## 复现与证据

证据目录：`audits/cq-mcp-capacity-20261026-01/`（Git 忽略，不随代码提交或入包）。

- `windows-full-r01.xml/.log`、`linux-full-r01.xml/.log`：第一批五项完整记录。
- `windows-process-r01.xml/.log`、`linux-process-r01.xml/.log`：独立进程补验。
- `windows-targeted-r01.xml/.log`：较早的连接竞争与真实取消定向两项，保留但不重复计数。
- `results.json`：从 JUnit 属性提取的场景指标、数量和耗时。
- `evidence-manifest.json`：测试、文档、日志、汇总的原字节摘要及体积。
- `collect_results.py`：重新提取和核对 JUnit 指标的脚本。

Windows 使用现有全局 Python/pytest，通过 `site.addsitedir` 加载既有 runtime-venv 的
pywin32 依赖；没有新建干净环境或安装依赖。这不替代之前的 wheel/sdist 安装验收。
Linux 使用已有 `/root/cq-mcp-linux-tests-20261025-01/bin/python`。
测试源码通过 `PYTHONPATH=<repo>/src` 选择，`CQ_MCP_CAPACITY_STRESS=1`。

可在具备既有依赖的解释器下执行：

```text
python -m pytest tests/mcp/test_capacity_stress.py -vv -s -o junit_family=legacy --junitxml=capacity.xml
```

实际第一批运行时尚未加入独立进程测试，因此是五项；补验使用
`-k eight_processes`。当前文件一次可收集六项。最终 lint/format 检查均通过。
WSL 启动器的 localhost 代理提示保留在原日志中，不是 MCP 运行错误；测试不联网。

## Spec 落点与剩余工作

本批补齐 T22 的真实计数上限、默认字节配额、预留结算、线程/进程不超卖、读取与取消
保留场景，并复验 T05 同 key 重用、T07 控制受理与清理、T12/T25 游标部分边界。
不据此关闭完整 T05/T07/T12/T25 或整个发布矩阵。

仍未覆盖物理磁盘满、SQLite 持久化故障、任务/游标/快照三种上限混合时的全部排列、
停止服务后清理 state 与残留 owner 的完整流程；用户锁/owner 不随 state 清理删除的契约不变。
真实宿主在配额耗尽、长同步 gate/diff、大输出和断开时的表现仍需独立验收。
本轮不改正式质量门；没有 commit、push、发布或外部模型复核。
