# 0.6.0rc1 包与许可预检

后续更新：本报告保留预检当时的结论与缺项；其宿主/权限/混合容量收尾见
[最终候选验收](final-matrix-0.6.0rc1.md)，不将历史结果覆盖成新测试。

日期：2026-10-26。结论：候选包、依赖许可及本轮安装验收通过；完整发布验收仍未完成。
没有创建tag、GitHub Release或PyPI版本。本记录不构成公开发布批准。

## 候选身份与修订

以d29aa28为固定源基线，加冻结工作区差量构建；source-manifest与candidate.patch均保留。
版本改为0.6.0rc1，避免与不含MCP的旧v0.5.2包混淆；__version__与项目元数据一致。
测试中重新发布当前run的五个固定版本字面量改取__version__，没有减弱断言。

包元数据改用MIT的License-Expression，LICENSE/NOTICE明确入包；对应构建后端要求hatchling≥1.27。
sdist排除内部openspec/changes记录；原仓库不删除，测试和公开使用文档仍保留。
首轮sdist带入22个内部文档，其中两个含本机路径，发现后修正并重建。

实装验收又发现POSIX解释器缺陷：Settings对venv Python链接resolve后，变成基础解释器，
丢失venv工具。这不是SDK回环能够证明的环境问题，已作为产品缺陷修复：冻结绝对路径而不解引用。
四种来源（CLI/env/config/default）使用真实独有模块验证；修前4失败，修后4通过。
项目/state仍按真实路径校验。本轮唯一运行逻辑修改为此解释器路径处理。

## 最终包

路径：`audits/cq-mcp-release-0.6.0rc1-20261026-01/release-candidate/packages/`。

| 文件 | 字节 | SHA256 |
|---|---:|---|
| ai_code_quality-0.6.0rc1-py3-none-any.whl | 144828 | 694fcbb27f70d79bdb7fb61b96b6372fa85945b35ba46de3631a3bf656e2e084 |
| ai_code_quality-0.6.0rc1.tar.gz | 209720 | 199770884f58c781849e54877e27c187619db4e207e785c654aa51705263eb93 |

45个产品Python文件逐一核对源快照/wheel/实际安装位置。包内版本、Python≥3.11、
两个CLI入口、MCP条件依赖、LICENSE/NOTICE一致。无audits、reviews、工作目录、
虚拟环境、内部change记录、数据库或本机用户名绝对路径成员。
已知脱敏模式扫描的命中经复核为测试假凭据及deepsec_adapter.py:46的中文隐藏提示常量，
不是真实凭据；不把模式检查表述为未知秘密的绝对检测保证。

最终文档刷新仅改变README/文档内容；仍将最终精确包重新安装到各独立环境后重跑四组stdio，
不将旧包结果冒称为本包结果。早期包和失败材料保留，但不是本表指定候选。

## 依赖与许可

核心CLI没有运行时依赖。MCP direct依赖仍为mcp2.3.0、Windows条件pywin32312。
Windows样本闭包30个分发包（含cq，即29个第三方），Linux29个（含cq，即28个第三方）。
对平台marker、extras传播、Requires-Python和已装版本约束逐边核验，均无缺失或版本矛盾。
两平台传递解析结果是具体样本，不是通用锁文件；原始版本表/constraints/许可原文摘要分别保存。

pywin32元数据PSF不是完整许可：包内还含Mark Hammond许可、Python、Scintilla、MIT和
adodbapi的LGPL-2.1-or-later。已核对原文并补充NOTICE及docs/third-party.md。
原始第三方许可文件已保留于本地证据，cq wheel/sdist不捆绑这些依赖。
未来若分发完整运行时或依赖wheel合集，需要按实际成员另核对，不能复用“仅cq包”结论。

## 运行验证

- Windows/Python3.13、Linux/Python3.11各自独立wheel/sdist安装；最终精确包四组SDK stdio均通过。
- 每组实际调用九工具，JSON text与structuredContent一致；未知键和显式null返回INVALID_ARGUMENT。
- 真实ruff扫描产生F821，gate/diff的质量失败是有效业务结果（isError=false）；未用合成finding替代。
- 无分析器的独立服务解释器明确得到cannot_judge；不是把skipped当通过。
- 真实pytest创建sleep子进程，取消后cancelled/cleanup=confirmed，并核对原出生身份不再存活。
- initialize均<5s；计时止于initialize返回，单独列tools/list，不把整会话耗时叫冷启动。
- 两平台核心无SDK环境只有cq distribution；UTF-8/cp936的version/help与缺extra启动各6项通过。
  CLI会固定UTF-8输出；这里验证cp936启动环境不会崩溃，不宣称输出字节变为GBK。
- Windows自扫468采集：452通过、16跳过（原12默认/平台项+新增4个POSIX venv用例）。
- Linux完整回归468采集：458通过、10默认/平台跳过。计数来自JUnit；Windows计数来自实际进度符号。
- 覆盖率4045/4811=84.0782%。diff新增0/修复0/仍存在5/豁免1；diff与A门均exit0。
  七工具ok，import-linter无契约配置skipped；未调整规则、阈值、正式.cq或豁免。
- ruff/check、format（88文件）、mypy（45源码文件）通过。

检测能力仍来自底层ruff/mypy/radon/vulture/pytest/import-linter/DeepSec，cq负责聚合编排；
本地A门不是Sonar官方评级。未重跑容量或真实ENOSPC，因为本次未改相应逻辑。

## 未关闭的发布条件

| 项目 | 当前证据 | 仍缺什么 |
|---|---|---|
| T19 两真实宿主 | ab3d484历史包有Claude/Kimi大结果、35秒等待、取消及不同断开；本候选四组SDK通过 | 本候选的双宿主真实质量失败/缺工具、实际同步gate/diff期限和取消矩阵；SDK不能代替宿主 |
| T07/T08/T26 完整排列 | 已有大量两平台控制/强杀/进程域证据，最新回归通过 | 任务表未关闭的剩余排列；本轮没有将未跑场景勾选 |
| T16 Windows ACL | Linux普通UID只读已验 | Windows真实只读ACL负控；本轮没有执行 |
| T22 混合故障与清state | 任务/游标上限、快照、竞争、独立ENOSPC及预留恢复已有证据 | 混合故障负载及清state/owner流程全链 |
| 历史CI偶发失败 | 一次stdio崩溃测试失败未保留具体栈，补诊断后的CI通过 | 若复发需用新日志定位；不能声称根因已修复 |
| 最终发布 | 具体候选、摘要、许可、安装与回退说明可审阅 | 必验补齐后确认渠道，再做公开固定版本安装复验；尚未归档change |

## 证据索引

根：`audits/cq-mcp-release-0.6.0rc1-20261026-01/`。

- release-candidate/build-review.json、source-manifest.json、candidate.patch、packages/SHA256SUMS：最终包身份。
- dependencies-windows/与dependencies-linux/：实际依赖、marker/Python约束核验、constraints和许可原文。
- smoke-final-{windows,linux}-{wheel,sdist}/：最终包SDK实际响应、冷启动、进程取消及缺工具结果。
- core-fixed-{windows,linux}/、installed-*.json：核心无extra与已装源码逐文件校验。
- venv-before.log、venv-after.xml、首次smoke-linux-*：解释器缺陷的修前失败和修后验证。
- selfscan-commands.json、scan/diff/gate.stdout/stderr、linux-fixed-regression.xml、verification.json：回归和A门。
- cq-mcp-rc-selfscan-20261026-01：正式自扫产物、输入/完成标记和coverage。

本轮未重新调用外部审核模型，也不把用户此前转交的独立意见冒称为本候选已经获签署。
