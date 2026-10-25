# cq 本地 MCP 冻结设计独立审阅

## 1. 总体判定

**有条件可实施。**

设计整体边界清晰、诚实地披露了自身未验证项，核心扩展（run ID 独占、原子建目录）与源码缺陷对得上。但存在一处“接口承诺与现有核心能力不匹配”的实质性缺口（F1），以及若干必须在实施前收口的语义歧义。F1 未解决前，`cq_diff`/`cq_gate` 两个工具的契约不可按设计原文实现。

---

## 2. Findings

### F-01 | 高 | design.md §3 工具注册表 / proposal.md 首版范围 vs cli.py:556-613、gate.py:106-116

**冲突证据**：
- design.md：`cq_diff` 参数为 `run_id, base_run_id`——“比较两个明确的完整 run ID，复用已有 diff 算法”；`cq_gate` 也接受 `base_run_id?`。
- 源码：`_run_diff_command` 的对比侧是 `load_baseline(project, args.baseline)`（cli.py:567），即 `audits/baselines/<name>.json` 文件，不是 run；`run_gate` 同样只接受 `baseline_ref`（gate.py:106）。核心 `diff_findings` 函数虽存在，但**没有任何 CLI 子命令支持“两个 run 互比”**。
- proposal.md 明确排除“新增持久化 baseline 写接口”，且 MODIFIED 表中 `cli.py` 仅新增 `--run-id`。
- 设计又规定 MCP 执行“固定 argv 子进程 / 同安装环境的 cq CLI”，不允许进程外传任意入口。

**可复现触发**：客户端调用 `cq_diff(run_id=mcp-xxx, base_run_id=20261024-…)`，适配层无法构造对应 CLI argv；`cq_gate` 带 `base_run_id` 同理。

**影响**：8 个工具中 2 个的核心契约不可实现，或被迫静默改变语义（如偷偷写 baseline 文件，违反排除项）。

**最小修订**：三选一并写明——(a) 首版 `cq_diff`/`cq_gate` 去掉 `base_run_id`，只做单 run 评估；(b) 允许适配层进程内 import `diff_findings`/`run_gate` 并将两个 `RunData` 临时传入（需修订“固定 argv 子进程”表述与进程回收章节对这类调用的覆盖）；(c) 在 MODIFIED 中新增 CLI 对“run vs run 比较”的最小支持并补验收项 T13。

**验证方法**：对照修订后设计逐条核对每个工具参数是否都有唯一确定的核心入口（CLI argv 或进程内函数），T13 场景改写为覆盖实际路径。

---

### F-02 | 中 | design.md §3 vs spec.md CQ-MCP-04

**冲突证据**：spec 要求“扫描 MUST 显式传递非空 adapter 列表，防止空值回退全部”；但工具 schema 中 `adapters?` 为可选，且 design 仅说“没有空 adapters 回退全部的路径”——**省略（undefined）与空数组的语义未定义**。而核心源码 `enabled_adapters or cfg.enabled_adapters`（scan.py:59）恰好存在空值回退配置的路径，若适配层直接透传省略值，就会触发被禁止的回退。

**可复现触发**：客户端调用 `cq_scan_start(request_key=…)` 不带 `adapters`。

**影响**：执行了未声明的 adapter 集合，违反 CQ-MCP-04 的可见性要求，pytest opt-in 边界可能间接失守（取决于项目配置）。

**最小修订**：二选一——schema 将 `adapters` 改为必填非空数组；或明确“省略 = 启动策略默认允许集合”，并在返回中如实际列表披露。修订后补一条 schema 一致性测试。

**验证方法**：`tools/list` schema 审查 + 省略/空数组/含 pytest 三种调用的行为测试。

---

### F-03 | 中（待确认）| design.md §3 status 过滤枚举 vs runs.py / 未提供的 schema.py

**冲突证据**：`cq_findings_get` 允许按 `status: new/existing/fixed/suppressed/accepted` 过滤，design 自认“核心目前没有独立 status 枚举常量”。从已给源码看，落盘 findings 的 status 只有 `suppressed`（scan.py:71 `_apply_suppressions`）可确认；`new/existing/fixed` 是 `diff_findings` 的**派生分类**，不一定存在于 findings.json 的 status 字段。

**可复现触发**：对任一已完成 run 调用 `cq_findings_get(status=["new"])`。

**影响**：若核心 status 字段不含这些值，过滤恒空或错误归类，客户端据此得出“无新增问题”的假结论。

**最小修订**：实施第一阶段核对 schema.py 与实际 findings.json 样本，将过滤枚举改为与落盘字段一致；若需 diff 分类过滤，明确其为服务侧派生并标注来源。当前标记为**待确认**，因 schema.py 与 diff.py 未随包提供。

**验证方法**：真实 run 产物字段枚举测试，写入 T11。

---

### F-04 | 中 | design.md §2/§5 vs config.py:82-98

**冲突证据**：design 称“tool-python 和 DeepSec 等配置属于用户启动配置；每次调用不能改变”，但核心 `Config.load` 读取进程环境变量 `CQ_*`（config.py:84-94），而 MCP 子进程必然继承服务进程环境。外部（用户 shell 或客户端宿主）修改这些 env 即可在服务存活期间改变每次调用的实际解释器选择，绕过“调用参数不能传环境变量”的边界。

**可复现触发**：以 `CQ_PYTHON=…` 启动 cq-mcp 服务，观察 doctor/scan 实际选择的解释器与 `python_source`。

**影响**：执行边界声明与实际行为不一致；恶意/意外 env 使扫描使用未受信解释器。

**最小修订**：设计明确服务启动时对 `CQ_*` 相关 env 的处理策略——启动时快照并冻结（对子进程显式传固定 env），或显式拒绝带这些 env 启动并在 doctor 中披露来源。

**验证方法**：修改 env 后调用 doctor，断言 `python_source` 与配置摘要不变。

---

### F-05 | 低 | design.md §5 “所有 CLI 执行型调用串行”

**冲突证据**：doctor、diff、gate 都是子进程执行且 gate/diff 有写副作用，但工具表中 doctor 标注 `readOnlyHint=true`、副作用仅为探测。哪些工具算“执行型调用”需持锁未列举，实施时易出现 doctor 与 scan 争锁返回 PROJECT_BUSY（过度串行）或 gate 写 gate.json 不持锁（不足串行）两种偏差。

**最小修订**：在 §5 列出每个工具的持锁矩阵（scan/diff/gate 持锁；doctor/job_get/findings/artifact 不持锁或只读共享）。

**验证方法**：T05/T07 增加并发 doctor 与 gate 的组合场景。

---

### F-06 | 低 | design.md §6 快照产物无界增长

**冲突证据**：“每次调用结果另存不可覆盖快照并登记 artifact_id”——无保留数量/期限策略。本地单用户长期使用将无限累积于 state-dir。

**最小修订**：增加简单保留策略（如按数量/天数清理，清理不影响已失效游标的正确报错路径）。

**验证方法**：清理后旧 artifact_id 返回 INVALID_ARTIFACT 而非读取错文件。

---

## 3. 值得保留的设计

1. **envelope 中“调用成功 / exit code / 质量判定 / 证据完整性”四层分离**（§4 + CQ-MCP-08），与 gate.py 实际的 skipped/error 语义精确对齐，避免最常见的质量门误读。
2. **run ID 最小核心扩展**：`mcp-<UUID>` + `exist_ok=false` 原子建目录，直接修复 scan.py:52-55 的秒级碰撞与静默复用缺陷，且不动旧命名兼容。
3. **request_key 跨重启去重与跨进程项目锁分离**（去重随 state-dir、锁随项目），幂等重试与互斥两个正交问题没有混在一起。

## 4. 未验证项与证据限制

- 本审阅仅基于审阅包内文本与源码节选，未执行任何扫描、安装、协议握手或客户端连接；所有测试编号均为计划而非通过证据。
- `schema.py`、`diff.py`、`doctor.py`、adapter 实现未提供：F-03 的 status 枚举问题、finding 字段形状、doctor JSON 结构均无法最终确认。
- MCP SDK 稳定版本、Python 兼容下限、两个真实客户端可用性：设计已声明待实施核查，本审阅无独立证据，不作为缺陷。
- 跨进程锁在 Windows/Linux 的实际行为（含 junction、符号链接越界、Job Object 回收）属平台实测项，静态审阅不能证明或证伪。
- `source-baseline.json` 与主仓 HEAD 声明未随包提供哈希原文，无法复核基线完整性。