# 0.6.0rc1 最终候选验收

日期：2026-10-26。本候选的开发验收完成，可以进入发布渠道确认。
产品源码、版本和冻结包没有改动；本记录补齐此前发布预检列出的宿主、权限、混合容量和进程边界。
没有创建 tag、GitHub Release 或 PyPI 版本；公开渠道安装复验、规格同步与归档仍是发布步骤。

## 固定候选与方法

产品提交：`4a3496860a163955ac4875048e49c4f1cec4a9d6`。
该提交 [CI 9/9 成功](https://github.com/lkdx0220/ai-code-quality-skill/actions/runs/40273489848)。
包与许可、四组干净安装、无 SDK 核心、回归和来源摘要见
[预检报告](release-readiness-0.6.0rc1.md)。本轮复用其中指定的精确 wheel：
144828 字节，SHA256 `694fcbb27f70d79bdb7fb61b96b6372fa85945b35ba46de3631a3bf656e2e084`。
sdist 209720 字节，SHA256 `199770884f58c781849e54877e27c187619db4e207e785c654aa51705263eb93`。
45 个产品 Python 文件与冻结包、安装位置相符；未重建包或调整规则、阈值、`.cq`、豁免。

本轮本地证据根：`audits/cq-mcp-final-matrix-0.6.0rc1-20261026-01/`。
`verify_matrix.py` 从原始 stdio 请求/响应、进程出生身份和数据库后验重新核验，
`verification.json` 为 `verified=true`。下文文件名均相对此根。
故障脚本只在隔离项目替换受控子命令或设置屏障；实际安装的产品代码未修改。
没有重新调用外部模型做独立审核。Kimi 测试由用户手动执行，Claude CLI 用作真实宿主验收。

## 两个真实宿主

Claude Code 2.1.203；Kimi Code 桌面文件 ProductVersion 1.1.3.0。
Kimi 的协议 clientInfo.version 实际为 `0.0.0`，不能把桌面版本冒充为 wire 字段。
本次协商协议为 2025-11-25，不推及全部客户端或协议版本。ZCode 保留历史连通性子集结论；
VS Code 未计通过。

| 场景 | Claude Code | Kimi Code |
|---|---|---|
| 九工具、doctor→scan→poll | 实际调用通过 | 实际调用通过 |
| 真实 ruff F821 | gate/diff exit 1，ok=true、isError=false；gate=fail | 相同 |
| 分析器缺失 | cannot_judge | cannot_judge |
| 真实 pytest 子树主动取消 | cancelled / cleanup=confirmed | 相同 |
| 大 finding、分页和大 diff | 合成夹具通过 | 相同 |
| 核心 60s 执行截止 gate / diff | 60.165s / 60.160s，CLI_ERROR | 60.092s / 60.095s，CLI_ERROR |
| 客户端 5s 超时 | 发 cancelled 通知，执行取消约 4.937s；后续 doctor 完成 | 发 cancelled 通知，执行取消约 4.979s；后续 doctor 完成 |
| 强杀隔离服务，再读取原 job | interrupted / confirmed；宿主重连 | 相同；界面未显式显示重连 |

真实坏代码扫描与基础 run 配置不同，所以这条 diff 的 `comparable=false`；没有宣称其可比。
可比大 diff 单独使用双方同配置的合成夹具：200 条低危 finding，第一条占位 72121 字符，
两次 artifact 读取 offset 为 0→512→1024，摘要相同；两页分别为 large-0/1/2 和 large-3/4/5。
diff 共 233453 字符，`core_inline=false`，完整不可变快照可分块读取。
这些是合成规模验证，不是分析器检出了 200 条真实问题。

60s 场景运行真实受控核心进程（等待 75s 并创建 95s 子进程），由产品截止与回收；
不是只延迟传输响应，也不代表自然核心计算性能。5s 场景由宿主超时触发协议取消。
Kimi trace 另有会话收尾的 AbortError 取消通知，全部保留；核验关联实际 Request timed out，
不把其他通知隐去或声称全日志只出现一次取消。

服务强杀先持有实际进程句柄/出生身份，确认 Job Object 回收父子进程，才结束 relay 传播 EOF。
两个宿主均出现新的服务/relay 启动与 initialize，且同一 job 只提交一次。
Kimi 原 job 为 `j-947560c542fb4e6f97ab991074c8eac1`，
终态 interrupted、cleanup=confirmed、state_persisted=true；错误为 Previous server exited，未重跑。
用户界面未观察到连接错误，与底层内部重连不矛盾。
Claude 另做宿主自身强杀：EOF 取消任务，SDK 后验确认 cancelled/confirmed；该 SDK 后验不计第二宿主。

所有已交付 cq 结果的 JSON text 等于 structuredContent，isError 等于 !ok。
canonical 双份响应预算均小于 64KiB；本轮观测最大 Claude 7612 字节、Kimi 11400 字节。
host.jsonl、trace.jsonl、启动命令、提示词、exit、控制器及进程后验分别保留。

## 权限、容量与进程边界

| 范围 | 实际验证与结果 |
|---|---|
| Windows 只读 | 隔离项目 63 个文件/目录应用真实 RX ACL，四项写入负控 WinError5；SDK stdio gate 历史/当前、diff、三快照成功；CLI 默认写盘 IO_ERROR/exit4；内容、DACL、Git 状态无变，finally 恢复 ACL |
| Linux 只读 | 普通 UID/GID 65534，0555/0444；写入负控拒绝，Service gate/diff/快照成功，41 文件和 Git 状态不变，CLI 写盘 exit4 |
| 混合默认容量，两平台 | 10000 游标后第 10001 STATE_LIMIT；1000 个小 job 接纳与 100 个 8MiB 快照混合尝试，接受 280 jobs/29 snapshots，其余 STATE_LIMIT；预留归零，旧结果/游标/幂等重用可读 |
| 容量耗尽叠加 SQLite 锁 | 真实 EXCLUSIVE 锁下 get/artifact/cancel <1s 返回 STATE_BUSY；解锁恢复，integrity_check=ok |
| state 迁移，两平台 | 停服务后将本轮 state 重命名为 retired-state，保留旧证据可读；新 state 为空，用户锁及 owner 字节/文件身份保持；未 spawn 的 creating owner 仍阻断 CLEANUP_FAILED |
| 进程边界，两平台 | 正常退出遗留子树、核心 timeout 子树均回收；预取消不 spawn；存活进程配故意过期 birth 不被误杀；未强迫 OS 自然 PID 重用 |
| 真正单分析器超时，两平台 | pytest adapter timeout_default=3，实际创建 90s 子进程；scan exit2/completed、工具 timeout、cleanup confirmed；父子出生身份消失；gate cannot_judge |
| 新鲜度期限，两平台 | 子命令先真实等待 65s 再运行 cq inputs；放宽至 120s 成功 verified_now/pass_with_gaps；设 1s 则 FRESHNESS_TIMEOUT/cannot_judge；预留0 |

Linux 只读 reader 使用已有 `/usr/bin/python3` 3.14 加精确 RC 安装 site-packages；
setup 使用安装 RC 的 3.11。此项是 Service 权限验证，不是新的 Python 3.14 完整兼容或 SDK 认证。
混合容量使用真实 Store、事务和项目锁接纳/结算，不是 1000 次实际分析器或 stdio 扫描。
65s 是受控等待验证可调期限，不是自然大仓库哈希性能；真实 32000 文件清单已有阶段证据。
两平台压力耗时受环境不同影响，不据此比较平台性能。

补充 `contract_edges.py` 两平台各 24 项通过：双方逐项 config/rules/ignore/suppression/tool-version/
consistency/缺字段负控、任一侧 legacy publication unknown 都不可比；运行列表跨页无重漏且
marker_present 不冒称 verified；10001 个实际目录项返回 INDEX_LIMIT；真实子进程输出 9MiB
触发 OUTPUT_TOO_LARGE 并保留分页/CLI 指引；Service 错误投影和四种退出码 envelope 另作合成注入。
后两项分别是实际捕获限制与注入错误映射，不声称跑出了四种真实分析器失败。

## 首轮失败与收尾

- Windows 混合探针错误地用 sqlite3 事务 context manager 代替 close，自己占住文件导致迁移
  WinError5。原失败 `mixed-windows/result.json` 保留；显式关闭后仅补验迁移尾部，
  `mixed-windows-retirement-r02.json` 通过，未覆盖或重复宣称整套压力。
- Linux 首次普通 UID 不能穿越 venv 链接目标所在的 /root，reader 启动前 EACCES；
  改用已有可访问解释器，产品未改。
- 首轮 PID 负控仍写入本探针存活 owner 的出生身份，产品正确阻断；修夹具的 owner birth，
  两平台新目录 r02 通过。旧探针结束、出生身份核对后通过正常 ProjectLock.acquire 恢复，
  `owner-recovery-{windows,linux}.json` 保存 clean 结果；未删锁或绕过守卫。
- 原始 trace verifier 初版假定取消通知总数为1，修成按超时原因关联；收尾通知全部保存。
- 一次汇总打印默认 cp936 解码中文失败，修为显式 UTF-8；不影响已成功验收。
  一次收尾命令选到默认 docker-desktop WSL、找不到解释器，明确指定 Ubuntu 后成功。

`probe-corrections.json` 记录上述探针问题。没有把探针修订包装成产品修复。
Kimi 工作区连接的空闲 MCP 服务是正常驻留；分析器/测试子树已核对回收。

## T01–T28 证据对账

表中“覆盖”指 spec 所列行为在注明的配置下有运行证据；不表示所有 OS/Python/客户端排列皆跑过。
默认 skip 不计通过；平台专用、压力、ENOSPC 已另行显式执行，见各阶段报告。
历史故障测试在当前提交回归/CI 中继续覆盖；本轮不重复执行所有旧屏障排列。

| 项 | 覆盖依据 |
|---|---|
| T01 | 预检的两平台 core-only/四组 wheel/sdist SDK；当前 CI 核心与 extra 分组 |
| T02 | 预检 initialize 单独计时<5s、九工具/未知键/null；test_service 协议与参数测试 |
| T03 | 核心两轮 review regressions 的路径/别名/junction；service 跨 state 锁；本轮真实只读权限 |
| T04 | test_core_evidence 空 adapter；test_service 枚举/策略/非法参数；宿主仅显式 opt-in pytest |
| T05 | test_service 去重/终态/跨 state，test_control_faults 写锁；本轮混合容量与 STATE_BUSY |
| T06 | test_core_evidence collision/发布；test_stdio_crash 接纳窗口；宿主返回固定 run_id |
| T07 | test_control_faults 竞争/受理/queued；本轮两平台正常/单分析器超时/预取消及宿主取消 |
| T08 | test_posix_recovery、test_operation_recovery、两平台阶段强杀；本轮 PID 身份负控和双宿主强杀 |
| T09 | core evidence/review 的 CLI 参数/碰撞/IO4；service 领域失败和 parse_output；本轮真实 timeout、缺工具及合成 error envelope |
| T10 | test_service skipped/history/stale/freshness；两宿主真实 fail/缺工具；无把 core.passed 直接当 verdict |
| T11 | core 发布/损坏/legacy 测试，test_storage_faults、stdio crash；宿主 verified 与 interrupted |
| T12 | test_service 中文/emoji完整分块、摘要损坏/游标漂移；容量 TTL/重启；两宿主大结果分页 |
| T13 | test_service 同名/未知版本/legacy、源码正常变动；本轮两侧逐项可比性负控 |
| T14 | 核心共享 inputs/新增删除/32k 清单；本轮两平台 >60s 可调期限与超时 |
| T15 | 核心 review 的 stdout/md/legacy/输入展示脱敏；service 日志/快照；受限 .env 路径设计与测试 |
| T16 | 本轮 Windows 真实 ACL + SDK、Linux 普通 UID + Service；CLI 写盘负控与快照不变 |
| T17 | 当前 CI specdrift-compat/core-only；CLI/Skill/DSH 阶段兼容记录和行为修正公告 |
| T18 | 预检两平台 wheel/sdist 四组干净安装及 UTF-8/cp936 启动 |
| T19 | 本轮 Claude/Kimi 九工具、真实失败/缺工具、大结果、60s核心期限/5s客户端取消、服务强杀重连 |
| T20 | 预检固定源码自扫/A门/覆盖率及 CLI 对照；本轮 host 实际计时/响应字节，首轮失败均保留 |
| T21 | 预检解释器四来源/initialize；test_service CONFIG_CHANGED，异步 doctor 及项目锁，docs 顺序 |
| T22 | capacity-validation 双平台上限与竞争；本轮混合负载+锁、state保留迁移与owner守卫 |
| T23 | test_core_evidence 每个发布写入点、test_storage_faults 原子失败/marker，覆盖 coverage present/absent |
| T24 | test_service 大diff/真实超限捕获；本轮两宿主快照及两平台 9MiB 捕获负控 |
| T25 | 宿主运行发现、当前 CI；本轮 legacy/marker语义、分页及实际 10001 项 INDEX_LIMIT |
| T26 | fault-recovery/operation-recovery 的 commit/spawn 屏障与当前 CI；本轮双宿主崩溃同job不重跑 |
| T27 | core inputs 无发布/不稳定；control 总期限；本轮真实 adapter timeout 及宿主60s/5s |
| T28 | 核心 Config snapshot 与 inputs 持久化；本轮 config/rules/suppression 缺失/不同不可比 |

## 证据与发布边界

主要记录：`verification.json`、`contract-{windows/result,linux-result}.json`、
`windows-acl/result.json`、`linux-readonly-result.json`、`mixed-linux-result.json`、
`mixed-windows/result.json`、`mixed-windows-retirement-r02.json`、`process-*-r02*`、
`freshness-*`，以及各 `claude-*` 与 `kimi-suite` 的 trace/host/control 文件。
原始日志按明确白名单归档，manifest 逐项摘要、ZIP CRC/成员集合核验；
不递归打包虚拟环境、项目树、state 数据库或约 243MiB 容量夹具。
本地归档为 `cq-mcp-final-matrix-0.6.0rc1-evidence.zip`，不自动上传外部。

尚未验证：Windows 真实满卷（有 Linux 实际 ENOSPC 和 Windows 注入）、所有客户端及协议版本、
最大 665s 配置的真实宿主等待、自然 OS PID 复用、所有规模仓库性能。
这些边界没有改写为已通过，也不是本次对外支持承诺。
历史 CI 一次 stdio 偶发失败仍无已证明根因；当前 4a34968 的九项 CI 全绿不抹去该历史。
下一步由用户确定发布渠道与最终版本，公开固定版本安装复验后再同步/归档 change。
