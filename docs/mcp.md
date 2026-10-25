# 本地 cq MCP（未发布候选）

cq MCP 把现有 CLI 接入本地 stdio 客户端。检测能力来自 ruff、mypy、radon、
vulture、pytest、import-linter、DeepSec；MCP 提供任务生命周期和证据约束，不新增检测算法。
使用者在自己的电脑执行，不经作者服务器。目标项目必须可信；分析器插件和测试可能执行代码。

**默认只选择 ruff-check / ruff-format / mypy / radon / vulture。** 五项正常且当前证据有效，
没有质量失败时是 `pass_with_gaps`，因为安全、架构、测试/覆盖率等未选。
显式选择 DeepSec 却缺工具，或显式选择 import-linter 却没配置，是 `cannot_judge`。
这表示证据不足，不能解读为服务损坏或质量通过。

## 候选启动

声明的可选依赖为 `mcp==2.3.0`，Windows 另需 `pywin32==312`。核心 CLI 仍无运行时依赖。
下列为候选构建后的安装/启动方法，不表示已上传 PyPI。Windows/Python 3.13 的
wheel/sdist 构建、缺 extra 边界和全新 venv 安装回环已经实测；证据见
`audits/cq-mcp-build-20261025-01/build-install-report.md`。这仍不代表跨平台或真实宿主发布验收通过：

```text
python -m pip install "/path/to/ai-code-quality[mcp]"
cq-mcp --project /absolute/trusted-project --state-dir /absolute/cq-state --tool-python /absolute/tool-python
```

源码环境等价入口为 `python -m ai_code_quality.mcp`（须配置 src 导入路径）。
服务解释器应有 MCP extra，`--tool-python` 是已有分析工具所在解释器；服务不自动安装工具。
优先级：显式参数 > 启动 `CQ_PYTHON` > 项目 cq.toml/.cq.toml > 服务解释器。
启动不遍历解释器或运行 doctor。环境与执行配置冻结，配置改变报 `CONFIG_CHANGED`，需重启。
缺 extra 时 stderr 提示安装可选依赖并 exit 2，stdout 不输出非协议日志。

客户端应启动该进程并使用 stdio。通用配置示例见 `examples/mcp/server.json`，其中路径需替换。
当前已用官方 SDK `ClientSession` 完成九工具 stdio 回环；Claude Code、VS Code 等真实宿主的
配置、长调用期限和断开取消仍待发布验收，不能套用未经验证的宿主时限设置。
本机协商协议为 2025-11-25；不能据此宣称支持所有客户端或更新协议。

## 九个工具

| 工具 | 主要输入 | 行为 |
|---|---|---|
| cq_doctor | request_key | 异步环境检查；通过 job_get 获取结果 |
| cq_scan_start | request_key，adapters?，timeout_seconds? | 异步全项目扫描，受理时返回 job_id/run_id |
| cq_job_get | job_id | 状态、期限、退出码及结果；发现已退出服务的遗留任务时安全恢复 |
| cq_job_cancel | job_id | 请求取消，终态须等待进程树回收 |
| cq_runs_list | cursor?，limit?，include_legacy? | 本 state 的任务及项目 run 索引；marker_present 不等于已验证 |
| cq_findings_get | run_id，severity?，status?，cursor?，limit?，verify_current? | 分页发现；超长 finding 返回 artifact 占位且推进游标 |
| cq_gate | run_id，target?，base_run_id?，verify_current? | 核心报告及独立证据判定；不改历史 run |
| cq_diff | run_id，base_run_id，verify_current? | 历史差量及可比性；不改历史 run |
| cq_artifact_get | artifact_id，offset?，length? | 登记过的脱敏快照；offset 为 Unicode 码点 |

ID 须完整，单级 ASCII 字母数字/下划线/连字符，最长 128；不接受路径、设备名、前缀。
run 和同名具名 baseline 冲突返回 `AMBIGUOUS_BASE_RUN`，不会偷偷采用另一份来源。
参数未知键、错误类型、空/重复 adapters 一律拒绝。pytest 同时要求启动
`--allow-test-execution` 和调用显式选择，启动授权不自动运行测试。

推荐顺序：doctor → job_get 等完成 → scan_start → job_get → findings/gate/diff。
doctor 全程持项目执行锁，不能与 scan 并行；新执行遇忙返回 `PROJECT_BUSY`。
同 request_key、同规范参数永远返回原任务（包括 cancelled/timed_out），`reused=true`。
需要重跑须换 key；同 key 异参为 `REQUEST_CONFLICT`。跨 state 共享项目锁但不共享去重记录。

## 读懂结果

`ok` / `isError` 表示调用是否取得合法结果。质量不达标仍 `ok=true`、`isError=false`。
最终质量结论看 `verdict`，不要只看核心 `passed` 或 CLI exit 0：

| verdict | 解释 |
|---|---|
| fail | 已验证的扫描版本有可信质量检查失败；仍应查看范围/时效限制 |
| cannot_judge | 旧/缺损证据、运行缺口、扫描输入不稳定、不可比基线或本次验证失败 |
| pass_historical | 显式未核对当前工作区，只证明历史声明范围；保留未测维度 |
| pass_stale | 历史通过，但当前监视清单已变化 |
| pass_with_gaps | 本次监视集合匹配，声明范围通过，仍有未选维度/跳过检查 |
| pass | 当前监视集合及所声明范围通过，无上述范围缺口；不保证检测无漏报 |

gate 默认 verify_current=true；findings/diff 默认 false。请求校验后超时不会降为历史通过。
快照读取的 freshness 总为 unknown，另存 freshness_at_snapshot；不能将旧 current 再当当前结论。
可比性要求两侧发布证据、配置/规则/工具版本等有效一致；未知版本不当相等。
正常源码改变允许比较。监视集合来自核心统一规则，不是分析器真实读取全集，也不是原子快照。

## 大输出、状态与副作用

工具返回 text 和 structuredContent 两份相同 envelope 1.2，总 wire 上限 64 KiB。
CLI stdout 硬上限 8 MiB、stderr 256 KiB。预算内大 gate/diff 返回摘要和完整脱敏快照引用；
超限为 `OUTPUT_TOO_LARGE`，可分页 findings 或退回 CLI，绝不解析截断 JSON。
artifact 分块用 next_offset，finding/run 分页用 next_cursor；内容变更或游标过期报 STALE_CURSOR。
仅登记快照可读，不接受任意路径，不开放 raw 文件、源码、.env、原 run gate.json/diff.json。
已知秘密模式统一脱敏，未知形态不保证检出。客户端自身可能将结果发送给其模型服务商。

scan 写项目 audits/ 及分析器缓存；doctor 启动探测子进程。gate/diff 用 --no-save，
历史 run 不被改写；即使只读查询也写有界服务审计日志。所有工具 annotations 保守为非只读。
state 必须在项目树外，含 SQLite 台账/快照/游标及轮转日志。state 只绑定一个项目。
总容量 256 MiB，预留 16 MiB 控制空间；每次执行临时预留 9 MiB，快照结算扣减，完成释放余额。
独立上限 1000 jobs / 10000 cursors（TTL 24 小时）；容量先到也会拒绝，不能保证用满计数上限。
读已有结果/取消保留。已确认清理的任务释放预留，cleanup_failed 保留阻断证据。

项目锁位于同用户固定缓存：Windows `%LOCALAPPDATA%/cq-mcp/locks`，
Linux `~/.cache/cq-mcp/locks`，按规范项目路径哈希；不写项目根，不改变项目 .gitignore。
跨 OS 用户、直接 CLI、网络文件系统不保证串行。Windows 使用挂起创建→Job Object→持久化身份→恢复。
正常退出也清理残留后代。Linux 使用进程组；服务遭 SIGKILL 后不承诺自动回收整棵树。
恢复必须确认旧进程域已空，不能按 PID 单独杀进程或只凭 OS 锁释放推断安全。

遇 CLEANUP_FAILED：停止该项目的服务，保留 owner 记录与 state，对照进程出生身份和任务域排查残留。
不应通过删除 owner/锁文件来强行解锁。清理 state 前停止服务、确认所有任务清理、导出所需证据；
另建空 state 不会绕过项目锁。当前不提供自动清理/修复工具。

## 时间预算和验收边界

doctor 600s；scan 默认 3600s，启动 --max-scan-seconds 范围 1..86400，调用不得超过它。
输入监视默认 60s，可用 --inputs-timeout-seconds 调至 1..600；gate/diff 核心计算 60s，清理宽限 5s。
gate 当前验证的默认最坏预算约 125s，最大配置约 665s；客户端至少再留 15s 协议余量。
超时、取消、未完成产物均不伪造空结果。实际宿主长调用/断开行为仍待验证。

当前开发证据覆盖 Windows / Python 3.13 与 Linux / Python 3.11；已验证真实进程树回收、
服务强杀恢复、两平台 SDK stdio 和边界回归，并有独立全新 venv 的 wheel/sdist 构建安装记录。
Linux 产品级进程恢复、第二个真实宿主、只读 ACL 与完整容量压力矩阵仍待验。
这是可供独立审核的实现候选，不是公开发布或全验收通过声明。CLI/Skill/DSH 可继续作为回退入口。
