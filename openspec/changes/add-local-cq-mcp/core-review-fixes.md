# 核心首批审核修订与复验（2026-10-25 / r02）

本轮处理 GLM / DeepSeek 的核心 r01 独立审核。作者已修复列明的进入服务层前问题并复验；本稿和 r02 候选尚未经过两位审核者再次独立复核。MCP 服务层仍未施工，本轮不代表产品可发布。HEAD 保持 `252ec3cf5bd3ca3024ab8dc0ee7111f6573ccad7`，未 commit。

## 修订结果

| 审核项 | 处理与验证 |
|---|---|
| DS P1：改 schema 关闭证据链 | marker、inputs、显式 schema 任一存在即要求新格式校验；未知/错误类型版本拒绝。3 / 字符串2 / 删除 / 浮点2 / 布尔值反例均拒绝；合法 legacy 保持可读 |
| DS P2-1：Windows 大小写 | 实际路径规范化后按真实目录身份校验；完整 ID 与前缀按平台大小写规则处理。Windows 实测通过 |
| DS P2-2：读取越界 | 单级 ID 校验、audits 对项目归属、run 对 audits 归属、legacy summary/findings 对 run 归属。实建 audits 根 junction 与 run junction 的越界负控均拒绝 |
| DS P2-3：脱敏缺口 | 输入规则 v2 先脱敏展示路径；path_sha256 保留原始路径身份，文件 sha256 仍按原字节；先形成公开结构再计算 monitor_digest。成功 scan JSON 同样脱敏。两个脱敏后同名文件不混并，改名仍改变摘要 |
| DS P2-4：adapter 集合歧义 | 明列 selected / attempted / completed / skipped；effective_adapters 是 selected 的兼容别名，不代表执行成功。skipped 的选定工具仍是 gap；attempted 指非 skipped adapter 结果，不证明每个子进程均成功启动 |
| GLM P2-1：非 UTF-8 崩溃 | marker/summary/findings 的二进制损坏均归 INVALID_ARTIFACT；gate/diff/triage/fix/suppress/baseline 六类 CLI 不裸崩溃；两次发布核验异常类型一致 |
| 其他采纳项 | 修正异常捕获顺序；记录 inputs_timeout_seconds；coverage 只 fsync 原字节，不经文本换行转换；扩 Basic/Bearer header 规则，保留正常 bearer 英文行文；exact 半写目录返回 RUN_NOT_READY |

全部意见的接受、延后及不同意理由见 `reviews/core-r01-disposition.md`。重复完整哈希的性能优化暂后移，不降低校验强度。输入监视仍不是分析器实际读取全集；root-only gitignore 子集不变；项目外源文件链接 fail-closed。README、适配器说明、proposal/design/spec/tasks 已直接同步契约。

## 实测

证据根：`audits/cq-mcp-review-fixes-20261025-01/`。每次命令记录 argv/cwd/PID/exit/耗时和独立 stdout/stderr，不覆盖 r01。最终扫描为 `audits/cq-mcp-core-20261025-04/`。

| 检查 | 结果 |
|---|---|
| 完整 pytest | 260 passed，0 fail / error / skip；原 214 项 + 46 项新反例。`full-final.xml`；其中 79 项在 tests/mcp，两组数字不相加 |
| ruff / format / mypy | 均通过；格式范围 src/tests 为 57 文件，mypy 为 31 源文件 |
| 核心无 MCP extra | 测试解释器未装 mcp；未修改 pyproject 依赖或安装新依赖 |
| 最终真实自扫 | 七工具 ok；import-linter 未配置 skipped；scan_consistency=consistent；完成标记可验证 |
| 覆盖率 | 2810 / 3357 = 83.70568960381293%；使用最终 run 的 raw/coverage.json 原始精度 |
| 输入清单 | 最终 run 的前后清单摘要均由规范对象复算；打包时再次匹配当前工作区监视摘要 |
| 32k 真实文件 | v2 完整输出 11,968,784 字节；summary 773 字节；两个命令 exit0；32,000 内容摘要一致。打包时再独立复算规范总摘要及全部路径身份摘要 |
| --no-save | 对最终 run 的全部文件做前后逐字节 SHA256 比较，无新增文件；gate/diff 仍输出有效业务结果 |
| 不变项 | 正式 .cq 原始 SHA、gate.py 原字节与原基线一致；diff.py 原字节与本轮开始一致，gate/diff 内容与 HEAD 一致；pyproject/.gitignore 原基线一致；不改阈值 |

32k 命令墙时 full 73.33870620000016 秒、summary 66.91461229999913 秒，预算各 120 秒。计时包含解析，并不等于内部监视时长；同机并行有其他验证活动，不能据此宣称吞吐退化比例或默认 60 秒必败。生成的临时文件树已清理；该实验不是 MCP 传输或客户端验收。

## A 门仍红

相对原基线：新增 2 / 修复 0 / 仍存在 0 / 豁免 1；gate A 与 diff 均 exit1。

1. `redact.py:46` 的 historical DeepSec blocker：仍是注释中的连接串占位示例；原 37 行登记只有 finding ID、无签名，新增规则使其漂移，现 ID 为 `75b368448e416b71c8c42f72af89570a04d0a3b8`。未重写登记换绿门。
2. `cli.py` 的 MI-C 为真实低危项，现值 7.267599723418189；不参与 A 门失败检查。继续列为服务边界整理时的技术债，不冒称已解决。

检测来自 ruff/mypy/radon/vulture/pytest/import-linter/DeepSec；cq 聚合编排，不新增这些分析器的检测能力。

## 失败轮与未验项

- 第一轮 79 项中 5 项失败：新 fsync helper 在 Windows 用只读句柄触发 Bad file descriptor；已改为不截断文件的 r+b 句柄，CRLF 原字节正控通过。首轮日志及 regressions.xml 保留。
- 初轮 lint 有三项，已修正；对应日志保留。
- 中间扫描 03 出现 run_scan CC-D(24)：adapter 集合统计引入了额外分支。已提取 coherent adapter summary helper，最终 04 不再出现该新增中危项；03 和其 facts 保留，但不是最终候选的完整源码快照。
- 首次 final facts 脚本把 Git blob 的 LF 与原工作区 CRLF 按字节误比，失败已保留；修为分别校验原基线字节和 HEAD 规范内容，未改产品代码规避。
- Windows 实测包含真实目录 junction；不以它代替 POSIX symlink、Linux 产品行为或 Python3.11 真机验收。完整矩阵、双真实客户端、打包安装、产品进程域/锁均尚未完成。
- fsync 只覆盖文件，无父目录 fsync 或断电事务保证；marker 非密码学签名，不能防御有权限者整体重写证据。原空 vscode-source-index.json 不作证据。

## 接续

作者复验未发现剩余的本批进入服务层阻断项；全量 A 门没有转绿。后续按任务表进入 MCP 协议/SQLite/OS 锁/任务生命周期，不把当前核心回归当作 T01–T28 完整产品验收。旧 r01 包、两份审核原文、原 baseline 和全部失败轮保持可追溯。
