# 核心 r02 复核后修订与复验（候选 r03）

2026-10-25。用户转交的 DeepSeek 与 GLM 两份复核分别为“修复列明问题后进入”和“可进入服务层”。两者都确认 r01 schema 绕过已修好。作者按具体反例修复，不以多数结论代替证据；当前候选尚无新增独立签署。

HEAD 仍为 `252ec3cf5bd3ca3024ab8dc0ee7111f6573ccad7`。未 commit/push/发布、未安装依赖、未改正式 `.cq`；MCP 服务层尚未施工。

## 处理结果

| 发现 | 本轮处理及验证 |
|---|---|
| DS P2-1 baseline 读取越界/损坏 | 基线读写逐层校验真实路径。实建 Windows junction，gate/diff/baseline 均拒绝外置数据；损坏对象、findings 元素、来源 ID 类型及非 UTF-8 归 INVALID_ARTIFACT/exit3。有效历史基线在源 run 删除后仍可读 |
| DS P2-2 非 UTF-8 文件名 | 实建含未配对代理字符的 Windows 文件名。inputs 和 scan 均为 INPUTS_UNAVAILABLE/exit2，不裸崩溃、不当参数错误、不发布 marker；保留失败目录且 ID 不重用 |
| DS P2-3 / GLM P2 输出泄露 | scan md 完整渲染后脱敏；真实 pytest usage error 不回显假 key。legacy gate/diff 的 JSON/md 与保存投影均脱敏，计算仍用原数据；no-save 不改原文件 |
| DS P2-4 selected/skipped | tools_ok 改为实际 ok/skipped 计数，不再声称全正常。全/部分 skipped 保留核心原有布尔与退出语义，不能据此宣称所有维度通过。MCP 必须独立判 runtime gap/cannot_judge，T10 明列反例，服务实现仍待办 |
| coverage 原字节声明错误 | 接受。原真实适配器会读文本、替换非法 UTF-8、转换换行并脱敏。只保证 scan 发布阶段保留适配器最终处理字节；原适配器不改。新增 LF/CRLF/非法字节/凭据路径四类测试调用实际 `_coverage_section`，再经过 scan/marker/读取验证 |
| Bearer 英文误删 | 脱敏规则版本升为 4；独立值需至少 8 字符并含数字或指定 token 符号，明确 Authorization 头及结构化值另匹配。保留 authentication/credentials/documentation 行文；纯字母独立 token 等仍可能漏检，未承诺识别所有秘密 |
| 相邻基线写问题 | 设备名、过长及路径式名称先拒绝；原子保存，替换失败保留旧字节并报 IO_ERROR/exit4，临时文件清理。未重写现存基线 |
| 文件被目录替代 | summary 目录为 INVALID_ARTIFACT；coverage 目录不能发布为 absent，无 marker |

逐项延后理由见 `reviews/core-r02-disposition.md`。更正生效于当前 README/proposal/design/tasks；旧 r02 包及历史 `core-review-fixes.md` 保留原样，其“分析器原字节”和“正常 bearer 全保留”等过宽声明由本文明确纠正。

## 当前实测

证据目录：`audits/cq-mcp-review-r02-fixes-20261025-01/`。命令均记录 argv/cwd/PID/exit/耗时/stdout/stderr，失败轮未覆盖。最终自扫：`audits/cq-mcp-core-20261025-05/`。

| 检查 | 结果 |
|---|---|
| 完整 pytest | 317 passed；0 fail/error/skip，JUnit 为 full-final.xml；其中 tests/mcp 136 项，不与总数相加。r02 的 260 项加本轮 57 个反例 |
| ruff / format / mypy | 通过；src/tests 格式 58 文件，mypy 31 源文件。最终自扫亦通过这些工具 |
| 自扫 | 七工具 ok；import-linter 无配置 skipped；scan_consistency=consistent；五类发布依赖 marker 校验通过 |
| 覆盖率 | 2908 / 3404 = 85.4289071680376%，来自最终 raw/coverage.json |
| 输入证据 | 前后规范对象摘要独立复算；当前工作区仍匹配最终 after 摘要；规则 v2 + 脱敏规则 v4 |
| no-save | 对最终 run 全部文件做 gate/diff 前后摘要和路径集合比较，无新文件、无改变 |
| 核心判据 | 与固定 HEAD 逐函数比较 gate AST，仅归一化 tools_ok 成功说明；评级、阈值、检查谓词、优先序及退出码一致。diff.py 内容/本轮原始字节、.cq/pyproject/.gitignore 原始摘要不变 |
| 无 MCP extra | 当前测试解释器仍未安装 mcp；原独占原型 venv 不代表产品服务已实现 |

32k 物理夹具本轮未重建或计时，未把旧吞吐数字称为当前实测。旧 r02 全清单/summary 证据可保留作历史复算，其规则 v3 摘要不能与当前 v4 直接比较。

## A 门与边界

相对 `cq-mcp-before-20261025`：新增 2 / 修复 0 / 仍存在 0 / 漂移 0 / 豁免 1；A 门与 diff 均 exit1。

1. `redact.py:53` 仍是注释中的历史连接串占位示例，DeepSec 报 blocker；旧 id-only 登记因行漂移失配，当前 ID 为 `081f9b3c010c3d7e007fa86397ee7194e7b84068`。未补登记换绿门。
2. `cli.py` MI-C 为真实低危项，当前 7.254428630809226，r02 为 7.267599723418189；本轮没有解决它。该项不参与 A 门失败谓词。

新增统计最初使 run_gate 达 CC-D(24)，已将统计说明提取为 helper；最终自扫不再有此项。初次 lint 的一个未使用导入已修，日志保留。另一次直接 ruff 有缓存写入警告但检查 exit0；扫描自己的缓存已重定向，不把警告写成工具缺失或质量通过依据。

检测来自 ruff/mypy/radon/vulture/pytest/import-linter/DeepSec；cq 负责聚合编排。

仍待服务层：T10 verdict、T13 run/baseline 同名拒绝及可信可比性、版本化 stdout 快照再脱敏、进程域/锁/SQLite/九工具/分页。CLI suppress --reapply 的损坏账本异常、gitignore 子集、目录 symlink 不跟随、prefix 遇逃逸 junction 整体拒绝、空失败 run 保留均有披露，未声称已完善这些行为。

Linux/Python3.11、文件级 symlink 特权路径、真实强杀/断电、构建安装及真实 MCP 宿主未在本轮验证；无全矩阵或产品验收结论。下一阶段为服务层实现，不把修订完成与产品发布混为一谈。
