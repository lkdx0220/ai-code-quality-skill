# cq MCP 服务首批候选实施记录

2026-10-25。用户授权“开始”后，在核心候选 r03 上实现服务层。HEAD 保持
`252ec3cf5bd3ca3024ab8dc0ee7111f6573ccad7`，未 commit/push/发布，未修改正式 `.cq`、
核心评级谓词/阈值或参考 DSH 仓库。本轮未安装依赖、未调用外部模型。不是独立审核结论。

## 已实现

- `src/ai_code_quality/mcp/`：可选 SDK stdio 入口，九个严格输入工具、envelope 1.2，text/structuredContent 一致。
- 固定单项目及解释器/环境；默认五个分析器；pytest 必须启动授权并显式选择。
- SQLite 幂等任务、事务容量预留、持久游标/快照、固定用户缓存项目锁及 owner 记录。
- 异步 doctor/scan，取消/总期限，Windows 挂起创建后加入 Job；正常 CLI 退出也清理后代。
- verified publication、未知工具版本不可比、同名 baseline 拒绝；skipped/历史/新鲜度与质量结论分开。
- 200KB finding 占位推进、完整大 diff 快照、Unicode 码点分块、内容变化拒绝与 64KiB 双份预算。
- run/job 索引的未验证头、容量分项、轮转调用日志；日志失败保留警告，响应仍有界。
- `pyproject.toml` 增加 `[mcp]`（mcp2.3.0，Windows pywin32 312）和 `cq-mcp` 入口；核心依赖为空。
- `docs/mcp.md`、README/适配器 README、通用无私人路径配置示例。

服务按职责分为协议协调 service、任务 jobs、质量执行 quality、分页 queries、证据 evidence、
进程域 processes、锁 locking、状态 store、契约 contracts、启动配置 settings。初版大 service 模块
MI-C 1.7939，拆分保留方法体后各新模块 MI A/B、无 CC-D；不会用豁免掩盖新增可维护性问题。

## 验证环境与证据

`audits/cq-mcp-service-20261025-01/verify.py` 保存每次 argv/cwd/PID/exit/耗时及 stdout/stderr。
已有 `audits/cq-mcp-preflight-20261025-01/.venv` 提供 SDK2.3.0/pywin32 312；以 PYTHONPATH
借用系统 Python3.13 的已装测试/分析器依赖。无新安装，这不是干净安装验收。

完整回归353项（其中核心317、服务36；tests/mcp共172）通过，无fail/error/skip。
服务用例包括真实 Windows 进程树正常退出/取消/超时/输出超限、owner强杀恢复、
受理中取消、终态key重用、并发去重、配置改变、发布/新鲜度/可比性、分页、快照、容量和日志。
真实SDK stdio脚本 `stdio_e2e.py` 执行全部九工具，逐次核对两份响应一致、总wire预算，
验证真实 F821 的 gate失败仍为有效领域响应。协议2025-11-25，非真实宿主。

独立构建/安装记录：`audits/cq-mcp-build-20261025-01/build-install-report.md`。该记录确认
wheel/sdist构建、缺MCP extra的明确失败边界，以及Windows/Python 3.13全新venv安装
`wheel[mcp]`后用真实 `mcp.ClientSession` 跑通九工具。它只覆盖该平台和SDK stdio回环，
不替代Linux/Python 3.11、两个真实宿主、容量/崩溃窗口和发布包内容审查。

core-only解释器启动MCP时stdout为空、stderr明确提示extra、exit2；原CLI回归仍通过。
产品server在子进程内执行，coverage未自动合并那些进程的记录；server.py显示0%不代表未跑握手，
不能反过来将端到端覆盖虚加到coverage百分比。

最终自扫为 `audits/cq-mcp-service-20261025-03/`，耗时61.03s；七工具ok，import-linter
无配置skipped，scan_consistency=consistent。最终pytest仍353项全部通过，覆盖率
3803/4573=83.16203804942052%。ruff/format/mypy通过（格式72文件、mypy44源文件）。
拆分后stdio九工具37次调用全部取得合法领域结果，initialize+list约0.713s，最大wire8430字节。

`audits/cq-mcp-service-20261025-01/final-results.json` 保存最终gate/diff及独立复算。
相对 `cq-mcp-before-20261025`：新增7、修复0、仍存0、漂移0、豁免1；gate A/diff均exit1。
blockers/highs/new_blocker_high未过；complexity、coverage通过，tools_ok仅表示无error/timeout，
不能掩盖import-linter skipped。

活动7项：redact.py:53历史注释占位串blocker、processes.py:129固定argv调用high、
cli.py历史MI-C低危，以及4条Windows STARTUPINFO属性被vulture误判未读的低危项。
这些属性由CreateProcess原生边界消费；作者解释不替代独立裁定，未改登记让门转绿。

复算通过：marker五依赖、前后规范输入摘要、当前monitor_digest、gate/diff --no-save前后
全部run文件路径及字节不变；冻结核心r03包内14个src/tests文件与当前逐字节相等；
正式suppressions摘要未变。新的服务候选不覆盖核心r03冻结包。

## 失败轮与处理

1. 首轮服务21通过/1失败：夹具的skipped AdapterResult漏reason，核心将其改为error。
   补有效reason，保留“全skipped不能被MCP判通过”的断言。
2. 第一次stdio全链脚本错误地把F401当high，实际为medium，核心正确允许通过。
   保存首版脚本和失败调用记录，改为真实F821未定义名，重新验证质量失败；未改质量门。
3. 一次doctor用相对venv解释器导致DeepSec探测失败；最终自扫改绝对解释器，并明确DeepSec解释器，
   不安装工具或把缺失说成通过。
4. 自扫暴露service MI-C，拆分模块；初次拆分有四处导入空行lint问题，修后ruff/format/mypy通过。
5. 新增processes.py的Popen调用被DeepSec标high。它使用受控列表argv、无shell；
   调用输入只允许固定工具/枚举/ID，启动解释器是受信配置。作者判断为通用命令执行规则误报，
   保留finding和红门，等待独立审核，不改正式豁免。

## 未完成的发布门槛

这批是服务实现候选，不是全矩阵验收：

- Linux产品进程组与强杀恢复、Windows文件symlink特权及只读ACL实测；Python3.11构建安装和SDK stdio子集已补验，见独立审计记录。
- 两个真实MCP宿主、长同步调用期限/断开清理、实际outputSchema兼容。
- wheel/sdist干净安装已在Windows/Python 3.13与Linux/Python 3.11子集完成；包内容、许可证/依赖发布复验仍待完成。
- 1000任务/10000游标及连续最大快照压力、SQLite故障/磁盘满/崩溃窗口的全矩阵故障注入。
- 大型真实仓库端到端、当前规则下物理32k重建；旧清单证据仅历史参考。
- 正式发布版本/渠道以及本候选的独立审核。

Windows已验证的具体例子不代替上述未跑边界。检测能力来自底层分析器，cq负责聚合、MCP负责传递和生命周期。
