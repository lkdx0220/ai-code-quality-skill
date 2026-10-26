# ai-code-quality（`cq`）· CLI / Skill / MCP

[![CI](https://github.com/lkdx0220/ai-code-quality-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/lkdx0220/ai-code-quality-skill/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**面向 Python 项目的本地代码质量工具**：`cq` CLI 聚合扫描、基线对比与质量门；
[`Skill`](agent-adapters/) 指导 Agent 分批修复；[本地 MCP](docs/mcp.md) 让客户端直接调用同一核心，
管理扫描任务、读取证据和取消执行。检测由底层开源工具完成，cq 负责编排与聚合。

> **🆕 spec-drift（可选 · v0.2.0→v0.5.0）**：采用 spec 驱动工作流（如 OpenSpec）的项目可启用
> **防漂移门**：`cq spec-gate` 强制"代码变更必须被 proposal 声明"（`--base/--range` 支持在
> CI 干净 checkout 与**已归档变更**场景下正确判定），`cq waiver` 提供带期限的豁免（到期翻红）；
> `cq spec-rebuild` 启发式对账（代码符号 vs spec 的线索清单）、`cq promote` 决策晋升候选。
> **默认关闭**：项目根放 `.specdrift.toml` 才启用，未配置的仓库行为逐项不变（CI 专项回归锁死）。
> 👉 详见下方 [spec-drift 章节](#spec-driftv020--可选spec-驱动项目的防漂移门)。

## 本地 MCP（0.6.0rc1 公开预发布）

MCP 实现及验收记录已合入 `main`，提供 **9 个本地 stdio 工具**：环境体检、异步扫描、
任务查询/取消、运行发现、finding 分页、gate、diff 和 artifact 分块读取。
扫描在使用者自己的电脑执行，无需作者提供服务器；目标项目必须可信，分析器和测试可能执行代码。
MCP 不开放修改源码、自动安装分析器、commit 或 push 工具。

从 PyPI 安装固定预发布版本（Python ≥ 3.11）：

```bash
python -m pip install "ai-code-quality[mcp]==0.6.0rc1"
cq-mcp --project /absolute/trusted-project --state-dir /absolute/cq-state --tool-python /absolute/tool-python
```

`--state-dir` 必须在项目树外；`--tool-python` 指向已经安装分析工具的 Python。
Windows 请换成相应绝对路径。客户端 stdio 配置示例：

```json
{
  "mcpServers": {
    "cq": {
      "command": "/absolute/mcp-venv/bin/python",
      "args": [
        "-m", "ai_code_quality.mcp",
        "--project", "/absolute/trusted-project",
        "--state-dir", "/absolute/cq-state",
        "--tool-python", "/absolute/tool-python"
      ]
    }
  }
}
```

Windows 的 `command` 示例为 `C:/path/to/mcp-venv/Scripts/python.exe`。
先调用 `cq_doctor` 并轮询到完成，再调用 `cq_scan_start`；默认选择五个静态分析 adapter。
pytest 须同时设置启动选项 `--allow-test-execution` 并在调用中显式选择。
安装、九工具参数、结果判定和客户端期限配置见[使用指南](docs/mcp.md)。

**当前验收状态**（2026-10-26；0.6.0rc1 已公开预发布，公开安装复验完成）：

| 范围 | 结果与证据 |
|---|---|
| Windows / Python 3.13 候选源码自扫 | 452 通过、16 默认/平台跳过；A 门 exit 0；覆盖率 84.08% |
| Linux / Python 3.11 候选源码完整回归 | 458 通过、10 默认/平台跳过 |
| Claude Code 2.1.203、Kimi Code 1.1.3 真实宿主 | 本候选九工具、真实质量失败/缺工具、大结果分页/分块、60 秒核心截止、5 秒客户端取消及服务强杀重连通过；任务不重跑 |
| ZCode | doctor → scan → poll 连通性子集通过 |
| 构建安装及恢复 | 两平台 wheel/sdist 构建安装与 SDK stdio 子集、进程树回收、SQLite 故障、Linux 受控真实 ENOSPC 已有阶段证据 |
| 0.6.0rc1 候选包 | 两平台 wheel/sdist 四组独立安装，九工具、真实质量失败、缺工具及实际进程取消通过；未当作真实宿主验收 |
| 权限及容量收尾 | Windows 真实只读 ACL、Linux 普通 UID；两平台混合容量/SQLite 锁、保留旧 state 的迁移及 owner 守卫通过 |

60 秒场景运行受控核心进程，5 秒场景由客户端超时发起取消；不是自然计算性能基准。
7 个分析工具正常；import-linter 因本仓无架构契约配置跳过，不计通过。
详见 [A 门记录](openspec/changes/archive/2026-10-26-add-local-cq-mcp/a-gate-validation.md)、
[最终候选验收](openspec/changes/archive/2026-10-26-add-local-cq-mcp/final-matrix-0.6.0rc1.md)与
[完整任务表](openspec/changes/archive/2026-10-26-add-local-cq-mcp/tasks.md)。本轮宿主绑定 `4a349686` 的冻结候选包；
历史 `ab3d484` 验收另存，不混用版本声明。

MCP 已随 [PyPI 0.6.0rc1](https://pypi.org/project/ai-code-quality/0.6.0rc1/) 和
[GitHub 预发布](https://github.com/lkdx0220/ai-code-quality-skill/releases/tag/v0.6.0rc1) 分发。
两平台公开 wheel/sdist 安装、core-only 与 Windows uvx 启动复验通过；VS Code 未记为已通过。

这是 **`0.6.0rc1` 预发布版**，旧 `v0.5.2` 标签不含 MCP；尚未发布 `0.6.0` 稳定版。
发布范围、安装与回退见[版本说明](docs/releases/cq-mcp/0.6.0rc1.md)，
MCP 安装依赖及 pywin32 多组件许可见[第三方许可](docs/third-party.md)。

<details>
<summary>核心证据扩展与 CLI 兼容边界</summary>

```bash
cq scan --project . --run-id local-review-01 --inputs-timeout-seconds 120 --format json
cq inputs --project . --summary --timeout-seconds 120
cq gate --project . --run local-review-01 --no-save --format json
cq diff --project . --run local-review-01 --baseline baseline --no-save --format json
```

`--run-id` 独占创建，已存在报 RUN_COLLISION，不覆盖；ID/读取前缀仅允许单级字母数字、
下划线与连字符（不含设备名）。显式空 adapter 列表拒绝；省略保留 CLI 旧默认。
`inputs` 不执行分析器；默认逐文件完整清单，`--summary` 只回规则/范围/计数/摘要。
监视期限默认每阶段 60 秒，可调 >0..600 秒；超时不发布完成标记。

新 run 最后写 `.complete.json`，校验五类发布依赖（coverage 可 absent）；该标记证明
发布完整性，不是质量通过或密码学签名。旧合法 run 可读；修改版本字段不能绕过新格式验证。
run 与依赖的真实路径须留在项目 audits 内；项目外源文件链接会使监视明确失败。
此监视集合采用根 `.gitignore` 子集，不等于分析器实际读取全集，也不是原子工作区快照。
具名基线读写也检查真实归属；形状/编码损坏报 INVALID_ARTIFACT。基线名采用相同的
单级 ID 限制。不能编码为 UTF-8 的文件名报 INPUTS_UNAVAILABLE/exit 2；失败 run
可保留空目录用于定位，但不发布完成标记，也不复用该 ID。

输入规则 v2 的 `path` 是已知规则脱敏后的展示路径，`path_sha256` 保留原始相对路径身份，
`sha256` 是文件原字节摘要；脱敏后同名的两个文件不合并。规范结构先脱敏再计算
`monitor_digest`，复算时排除 `monitor_digest/files_count/checked_at` 三项。
`redaction_rules_version` 纳入摘要；规则版本不同不可直接比较。未知秘密不保证全部检出。

summary 中 `selected_adapters` 是选定范围，`attempted_adapters` 排除 skipped，
`completed_adapters` 只含 ok；`effective_adapters` 保留为 selected 的兼容别名。
选中但跳过不等于通过。`inputs_timeout_seconds` 记录各监视阶段期限。

`--no-save` 不写历史 run 的 gate/diff；默认仍保存，但文件改为紧凑排序键 LF JSON。
新增 IO_ERROR 使用 exit 4；质量未达标仍为 exit 1。coverage 适配器会做文本转换及脱敏，
发布阶段只保留适配器最终处理后的字节并 fsync，不承诺与分析器原始字节一致。
原子临时输出在 POSIX 默认 0600；不承诺目录 fsync 或断电事务。
scan 控制台和 gate/diff 输出、保存投影（包括旧 run）应用当前脱敏规则；不会改写旧输入。
独立 Bearer 仅匹配至少 8 字符且含数字或指定 token 符号的值；Authorization/Basic/Bearer
明确头上下文另行匹配。纯字母独立 token 等未知形态仍可能漏检。
核心 gate 的 tools_ok 仅检查 error/timeout；skipped 计数已单列，核心 exit 0
不等于所有维度通过。MCP 独立处理 runtime gap/verdict：默认五项正常可为
`pass_with_gaps`；显式选中的工具缺失为 `cannot_judge`；历史结果不等于当前代码合格。

</details>

## 它解决什么问题

AI 编程助手让"能跑的代码"变得廉价，也让这类问题变得高频：

- 空 `except` 吞错、`NotImplementedError` 占位、复制粘贴的重复实现
- 零类型标注、圈复杂度爆炸的百行函数、测试覆盖率接近零
- 硬编码密钥进了仓库、`debug=True` 直接上线
- 修 A 坏 B：没有基线，改动无法归因，"上次到底改好了没有"说不清

传统应对只有两条路：**人肉审查**（不可复现、不可审计、换个 AI 结论就变），或者**上 Sonar**
（要服务器/账号/联网，规则黑盒，AI 也只是拿到一个分数）。

这个 skill 是第三条路：把"从烂到 A"的整套工作流**本地化、可复现、可审计**——

- **检测交给 8 个开源工具**（ruff/mypy/radon/vulture/pytest/import-linter/DeepSec…）：
  规则透明、版本可查、人人可复现；
- **聚合交给 cq**：统一 finding schema、统一严重度与产物链、基线对比、质量门判定、豁免留痕；
- **语义与执行交给 AI Agent**：读报告定批次、动手修（每一步经你批准）、运行时验证行为——
  这些是确定性工具做不了、而 Agent 真正擅长的事。

## 语言支持边界（重要）

**当前版本只支持 Python 仓库。** 8 个检测工具里 6 个是 Python 生态原生工具
（ruff/mypy/radon/vulture/pytest-cov/import-linter），扫描目标发现、`cq fix` 的自动修复、
`spec-rebuild` 的符号提取（AST）也都基于 Python 假设。Java/Go/TS 等语言目前
`cq scan` 会因找不到 `.py` 目标而得到空结果（spec-gate/waiver/promote 除外，见下）。

**语言无关、任何仓库都能用的部分**：`spec-gate` / `waiver` / `promote`（只依赖 git 与
markdown 文本，与代码语言无关）、账本与豁免留痕、报告与产物链、多 Agent 适配层。

多语言支持（Java：Checkstyle/SpotBugs/PMD/JUnit+JaCoCo/ArchUnit 等）在路线图上，
体量相当于重做一遍 adapter 层，按真实需求排期。

三者各干各的，谁也不替谁编造结论。

## 它如何运作

**SKILL.md 是 Agent 的工作流说明，cq 是确定性的执行核心，CLI 和 MCP 提供调用入口。**
下图展示 Skill 驱动 CLI 的路径；MCP 在同一核心外增加协议、异步任务和证据读取约束。

```
你："帮我审一下这个项目的代码质量"
         │
         ▼
┌────────────────────────────────────────────────┐
│ AI Agent（DSH / Claude Code / Codex / ZCode /…）│
│  读 SKILL.md：何时调 cq、怎么分批、何时必须停下问你 │
└───────────────────┬────────────────────────────┘
                    │  cq scan / triage / fix / gate …
                    ▼
┌────────────────────────────────────────────────┐
│ cq CLI（确定性执行核心，纯标准库、零运行时依赖）    │
│  解析扫描目标 → subprocess 调 8 个外部工具        │
│  → 统一 finding schema → 密钥脱敏                │
│  → 落盘 audits/<run_id>/（summary/findings/     │
│     report/gate/fix-plan/diff，全部可复核）       │
└───────────────────┬────────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────────────┐
│ ruff   mypy   radon   vulture   pytest   DeepSec │
│       （检测能力全部来自开源工具，cq 不重新发明）    │
└────────────────────────────────────────────────┘
```

工作流是一台状态机，每一步都有命令、有产物、有退出码：

```
scan ──► triage ──► baseline ──► fix（分批+跑测试）──► rescan ──► diff ──► gate
 │                                                  ▲                   │
 └────────────── suppress 豁免（必须写理由，落盘留痕）◄───── 未达标就再来一轮 ◄──┘
```

关键机制（详见下文各节）：

| 机制 | 解决什么 |
|---|---|
| 统一 finding schema（sha1 id / severity / category） | 8 个工具的输出变成同一种货币，diff/gate 才有比较基准 |
| 产物链 `audits/<run_id>/` | 每次扫描都有 summary/findings/report/gate JSON，可复核可对比 |
| 基线 + diff（行号漂移不算新增） | "修 A 坏 B"当场现形：新增 blocker/high，diff 退出码直接非 0 |
| gate 质量门（0/1/2/3/4 退出码） | 达标=0、未达标=1、工具执行错误=2、配置/加载错误=3、产物 IO 错误=4 |
| 豁免留痕 `.cq/suppressions.json` | 误报不是口头说说：理由、时间、来源 run 全部落盘可评审 |
| apply 门禁 | 源码修复通过 `fix --apply` 显式授权；扫描写审计产物，MCP 不开放源码修改工具 |

## 端到端：一次完整的质量修复长什么样

以下是一次真实运行（本仓库自举，数字可复核）：

1. **你说**："帮我审一下这个项目的代码质量。"
2. **Agent 体检环境**：`cq doctor`——8 个工具谁没装、装到哪个解释器，缺了先问你。
3. **Agent 全量扫描**：`cq scan` → 控制台给出工具状态表 + 分级统计，
   `audits/<run_id>/report.md` 里是每条 finding 的文件/行号/规则/证据（密钥已脱敏）。
4. **归因**：`cq triage` 把 findings 分成四维（安全/可靠性/可维护性/测试）并给出批次建议——
   例如"安全类先人工核对、188 条可自动修复放最后"。
5. **固化基线**：`cq baseline`——从这一刻起，"修没修好、有没有引入新问题"有了裁判。
6. **分批修复**：自动批次 `cq fix --batch 1 --apply`（要你批准）；复杂度/安全批次按指引人工修；
   每批跑测试。
7. **复扫对比**：`cq diff` → "新增 X（其中 blocker/high N）/ 修复 Y / 仍存在 Z"；
   行号漂移不算新增，格式化 100 个文件不会制造 300 条假警报。
8. **验收**：`cq gate --target A` → 逐项检查 + local_rating 评级 + 退出码；
   AI 据此向你汇报："还差覆盖率一项，其余全绿。"

早期自举曾将 **73 条 findings 收敛到 3 条**。加入 MCP 后，最新源码再次自扫：
**A 门通过，blocker/high 为 0，覆盖率 84.12%**；仍有 5 条 low 提示和 1 条既有豁免，
不是零告警声明。数字与跳过项见上方验收记录。

## 30 秒上手

```bash
# 一行安装（任选其一）
pipx install git+https://github.com/lkdx0220/ai-code-quality-skill
uv tool install git+https://github.com/lkdx0220/ai-code-quality-skill
pip install -e .   # 开发态

cq doctor                     # ① 环境体检：缺什么工具，按提示装（系统已有会自动发现）
cq scan --project <你的仓库>   # ② 扫描 → audits/<run_id>/report.md
cq gate --run <run_id> --target A   # ③ 质量门：blocker/high/复杂度/覆盖率/新增，exit 0=达标
```

## 怎么接进你的 AI Agent（适配器矩阵）

| Agent | 接法 | 文件 |
|---|---|---|
| DSH | 复制到各 home 的 `skills/ai-code-quality/` | [`agent-adapters/dsh/SKILL.md`](agent-adapters/dsh/SKILL.md) |
| Claude Code | 复制到 `~/.claude/skills/ai-code-quality/` | 同上（SKILL.md 通吃） |
| Codex | 片段追加到项目/用户级 `AGENTS.md` | [`agent-adapters/codex/AGENTS.md.snippet`](agent-adapters/codex/AGENTS.md.snippet) |
| Cursor | 放进 `.cursor/rules/` | [`agent-adapters/cursor/ai-code-quality.mdc`](agent-adapters/cursor/ai-code-quality.mdc) |
| 任何 Agent | 直接整份喂给模型 | [`agent-adapters/generic/PROMPT.md`](agent-adapters/generic/PROMPT.md) |
| 支持本地 stdio 的 MCP 客户端 | 安装 `[mcp]` extra，注册 `cq-mcp` | [`docs/mcp.md`](docs/mcp.md) |

装好后对 Agent 说"帮我审一下这个项目的代码质量"即可；各 harness 安装点与同步命令见
[`agent-adapters/README.md`](agent-adapters/README.md)。

## 设计原则

- **核心 CLI + 薄适配层**：`cq` 不依赖任何 Agent 框架（DSH/Codex/ZCode 各自只需一份说明文件，见 `agent-adapters/`）。
- **核心零运行时依赖**：CLI 只用 Python 标准库；MCP 可选依赖官方 SDK，Windows 另需 pywin32；分析器通过子进程调用。
- **不许静默 pass**：工具缺失/超时/解析失败 → `skipped` / `timeout` / `error` + 原因，绝不当作通过。
- **默认不改源码**：扫描产物及分析器缓存写入 `audits/`；MCP 另写项目外 state 和用户级锁，不自动 commit。
- **扫描范围与工具对齐**：扫描遵循目标仓库根 `.gitignore`（目录名/通配/相对路径的轻量子集，
  支持单段目录名、basename 通配、精确相对路径及其子树；不支持带斜杠的目录模式/通配、
  `!` 否定和嵌套规则）。`respect_gitignore = false` 可关闭此过滤，不代表完整 gitignore 实现。
  输入遍历不跟随目录符号链接；文件链接另做归属校验。前缀命中逃逸 junction 时整体拒绝，
  不跳过它继续挑选其他 run。
- **脱敏**：密钥/token 在任何产物落盘前统一替换为 `***REDACTED***`（含 raw 原始输出）。
- **离线**：DeepSec L3 / SonarCloud / AI review 一律 opt-in，当前版本未实现、不会调用。

## 开源工具声明与致谢（必读）

**cq 是扫描编排器（orchestrator）：它不包含、不分发、不修改下列任何工具的源代码**，
只是在运行时通过命令行调用用户环境中已安装的这些工具，并聚合其输出。
全部检测能力来自这些优秀的开源项目，版权归各自作者，遵循各自许可证：

| 工具 | 在 cq 中的作用 | 许可证 | 上游 |
|---|---|---|---|
| [ruff](https://github.com/astral-sh/ruff) | lint、未使用导入、危险写法、格式检查 | MIT | Astral |
| [mypy](https://github.com/python/mypy) | 静态类型检查 | MIT | python/mypy |
| [radon](https://github.com/rubik/radon) | 圈复杂度、可维护性指数 | MIT | rubik/radon |
| [vulture](https://github.com/jendrikseipp/vulture) | 死代码检测 | MIT | jendrikseipp/vulture |
| [pytest](https://github.com/pytest-dev/pytest) | 测试执行 | MIT | pytest-dev |
| [pytest-cov](https://github.com/pytest-dev/pytest-cov) | 覆盖率统计 | MIT | pytest-dev |
| [import-linter](https://github.com/seddony/import-linter) | 架构依赖契约检查 | **BSD 2-Clause** | seddony/import-linter |
| [DeepSec](https://github.com/Unclecheng-li/DeepSec) | 安全扫描 L1/L2（硬编码密钥、危险写法、注入） | MIT | Unclecheng-li/DeepSec |

cq 自身代码为原创，以 MIT 许可证发布（见 `LICENSE`）。
可选 MCP 安装另依赖官方 SDK 及 Windows 的 pywin32；其传递依赖和多组件许可另见
[第三方许可](docs/third-party.md)与随包附带的 `NOTICE`，不能把整个安装环境统称为MIT。
如果你在报告中引用 cq 的扫描结果，建议同时注明底层工具，例如
"扫描结果由 ruff / mypy / radon / vulture / pytest / import-linter / DeepSec 产出，cq 聚合"。

## 前置工具：跑 `cq doctor`，缺什么按提示装

cq 是编排器，检测能力来自上表 8 个外部工具，**它们需要你自行安装**（cq 不捆绑、不自动安装）。
装没装齐，一条命令看结果：

```bash
cq doctor                # 人读：✅/❌ + 版本 + 缺失工具的安装命令
cq doctor --format json  # 给 AI Agent 消费（见 agent-adapters/generic/PROMPT.md 的 bootstrap 纪律）
```

**解释器提示（uv tool / pipx 安装的必读）**：cq 装在隔离 venv 时，默认只探自带的解释器，
系统 Python 里已装好的工具链它一开始看不见——别急着 pip install 重装一遍。
doctor/scan 已内置兜底：默认解释器缺核心工具时自动改用 PATH 上工具链全齐的系统 Python，
并在输出里给出固化命令（`CQ_PYTHON` 环境变量 / 仓库根 `cq.toml` / `--python`，任选其一）。
deepsec 的源码仓库路径同理用 `CQ_DEEPSEC_HOME` 固化。显式复核：

```bash
cq doctor --python <系统python.exe> --deepsec-home <DeepSec仓库路径>
```

手动安装（装进 cq 使用的那个 Python，默认当前解释器，`CQ_PYTHON` 可覆盖）：

```bash
# 一次装齐 6 个核心+可选（MIT 许可，PyPI 直装）
pip install ruff mypy radon vulture pytest pytest-cov import-linter

# deepsec 二选一：
pip install git+https://github.com/Unclecheng-li/DeepSec        # 形态一：pip 安装
git clone https://github.com/Unclecheng-li/DeepSec <任意路径>    # 形态二：源码 + 环境变量
set CQ_DEEPSEC_HOME=<clone 出来的路径>                            #   cq 经 PYTHONPATH 调用，无需安装
```

实测通过的版本（2026-10 · Python 3.13 · Windows）：ruff 0.16.9、mypy 2.3.1、radon 6.0.1、
vulture 2.16、pytest 9.1.1、pytest-cov 7.1.0、import-linter 2.15、deepsec 0.2.0。
ruff 等工具的默认规则集会随版本变化，跨版本对比扫描结果时留意。

缺工具不会阻塞 `cq scan`（对应工具显示 `skipped` + 原因），但相应维度没有结论；
其中 ruff/mypy/radon/vulture/pytest 是核心，pytest-cov/import-linter/deepsec 属可选增强。

### 受限环境（CI 容器 / 只读缓存 / 杀软拦截）怎么跑

临时目录或缓存不可写时，工具会以各种姿势崩溃——cq 会把崩溃**如实报为 error 而不是静默当 ok**
（含"pytest 退出码 1 但零结果"的启动崩溃防御），但更好的做法是主动重定向：

```powershell
$env:TEMP = $env:TMP = "<可写目录>"                          # 临时目录
ruff check --no-cache src tests                              # 免缓存
ruff format --check --no-cache src tests
mypy --cache-dir "<可写目录>/mypy" src                       # 缓存重定向（被拒时会伪装成 INTERNAL ERROR）
pytest tests --basetemp="<可写目录>/pt" -p no:cacheprovider  # 注意：basetemp 不能是 cwd 或其父目录
```

看到 `mypy INTERNAL ERROR` 或 `pytest No usable temporary directory` 时，先查写权限再怀疑工具本身。

工具装在工作区 venv（如 `.cq-venv`）时，显式指给 doctor 验证（**不要据此重装工具**）：

```bash
cq doctor --python "<工作区>/.cq-venv/Scripts/python.exe"
```

## 安装与运行

```bash
# 方式一：装到 PATH（推荐，供任何 Agent 直接调 cq）——非 editable，源码复制进 venv
uv tool install git+https://github.com/lkdx0220/ai-code-quality-skill   # 发布用户
uv tool install .                                  # 本地源码（构建快照，改码后需 --force 重装）
pipx install .                                     # 或 pipx

# 方式二：开发态（改码即生效）
PYTHONPATH=src python -m ai_code_quality scan --project <目标仓库>
# 或 uv tool install --editable .（见下方启动故障警告）

# 隔离 venv 里没有 ruff/mypy 等工具时，用 CQ_PYTHON 指到装了工具的解释器：
#   set CQ_PYTHON=C:/Python313/python.exe
```

### ⚠️ 启动入口故障：`uv trampoline failed to canonicalize script path`

`--editable` 安装会让 uv 的启动器（trampoline）依赖**源码目录路径**。已知组合
"editable + 非 ASCII 源码路径（如 `skills开发`）+ 受限执行环境（沙箱掩蔽工作区外路径）"
会让 `cq`/`cq --help` 在 trampoline 阶段直接失败（进不了应用；uv 的部分子命令还会报
`os error 183`）。Codex/受限沙箱环境实测复现，干净终端可能正常——更具迷惑性。

**机器级环境变量注记**：`CQ_PYTHON` 这类变量是**隐式全局状态**，建议各环境自管
（需要扫描能力的会话显式设置；不设时 cq 回落默认解释器，缺工具会**明确报缺**而非静默用错）。
若曾设置后想移除：删除用户级 `CQ_PYTHON`（PowerShell：
`Remove-ItemProperty HKCU:\Environment -Name CQ_PYTHON`），恢复命令：
`setx CQ_PYTHON "<你的Python313路径>"`。维护者可另建不入库的本地包装脚本一键注入。

**解释器三层关系（doctor 的 `python` 字段从哪来）**：
`uv receipt/venv 解释器`（装 cq 时 `--python` 指定的，只有 cq 自己）→ 可能被机器级
`CQ_PYTHON` 环境变量**抢先覆盖**。优先级：`--python` > `CQ_PYTHON` > `cq.toml` > 默认。
doctor 输出的 `python` + `python_source`（default/config/env/cli）标明实际解释器与来源；
**装 cq 的解释器 ≠ 工具所在解释器**，两者都可能需要显式指认。

**处理顺序（先分流，不要重装底层工具）**：

1. 判层：`python -c "import sys; print('ok')"` 正常、而 `cq --help` 报 trampoline 错误
   → 故障在**安装启动器层**，与应用无关。`PYTHONPATH=src python -m ai_code_quality.cli --help`
   能出帮助 → 进一步确认应用层完好。
2. 解：`uv tool uninstall ai-code-quality && uv tool install .`（**非 editable**，源码
   复制进 venv，trampoline 只引用 venv 内路径，沙箱/中文路径均不受影响）。
3. 若重装后仍失败且你处于沙箱环境 → 属沙箱对 uv 路径的掩蔽（可能伴随 `uv tool list`
   报 `os error 183`），换非受限终端执行，或改用方式二回退；并欢迎到本仓库 issue 反馈
   （附 uv --version、cq.exe 路径、错误全文、是否 editable 安装、源码路径是否含非 ASCII）。
4. **不要**因这个错误去重装 ruff/mypy 等底层工具——它们与此无关。

## 用法

```
cq scan --project <path> [--scope full|changed] [--format json|md] [--timeout N]
        [--adapters ruff-check,ruff-format,mypy,radon,vulture,pytest,import-linter,deepsec]
        [--python <解释器>] [--deepsec-home <DeepSec源码仓库>] [--deepsec-python <解释器>]
        [--no-deepsec]

cq doctor [--format json|md] [--python <解释器>] [--deepsec-home <路径>] [--deepsec-python <解释器>]

cq triage    --run <run_id> [--project <path>] [--format json|md]
cq baseline  --run <run_id> [--name baseline] [--project <path>]
cq diff      --run <run_id> --baseline <基线名或run_id> [--project <path>] [--format json|md]
cq gate      --run <run_id> [--baseline <基线名或run_id>] [--target A|B] [--project <path>] [--format json|md]
cq suppress  --run <run_id> --finding <id前缀≥8位> --action false_positive|debt_accepted --reason "必填理由"
cq suppress  --run <run_id> --reapply                # 存量豁免按签名对齐到新 run（行号漂移后用）
cq fix       --run <run_id> [--batch N] [--apply] [--project <path>] [--format json|md]

# 以下两条需要项目根存在 .specdrift.toml（见「spec-drift」章节），否则旁路
cq spec-gate --mode soft|hard [--paths a,b] [--base <ref>|--range A..B] [--project <path>]
cq waiver     --reason "必填理由" --ttl 30m|12h|7d [--change <id>] [--project <path>]
cq spec-rebuild [--from code] [--draft|--apply] [--json] [--project <path>]  # 启发式对账（默认 --draft 只读）
cq promote     [--id <decision标识>] [--project <path>]   # 晋升候选与草稿，永不写文件
```

`scan` 退出码：`0` 完成；`1` 参数错误；`2` 有工具 error/timeout（结果不完整但不丢弃）。
`doctor` 退出码：`0` 全部工具就绪；`2` 有缺失（不阻塞 scan，供脚本/Agent 判断）。
`diff` 退出码：`0` 无新增 blocker/high；`1` 有新增（供 CI/Agent 直接判断）；`3` run/基线解析失败。
`gate` 退出码：`0` 达标；`1` 未达标（含新增 blocker/high）；`2` 工具执行错误（结果不完整）；`3` 配置/加载错误。

## Phase 2 工作流：基线 → 修复 → 对比 → 质量门

```bash
cq scan --project .                          # 1. 全量扫描
cq baseline --run <run_id> --name baseline   # 2. 固化为基线（自包含，源 run 删了也能用）
#   ……分批修复，一次只修一类，每批跑测试……
cq scan --project .                          # 3. 复扫
cq diff --run <新run_id> --baseline baseline # 4. new/fixed/existing/suppressed
cq gate --run <新run_id> --baseline baseline --target A   # 5. 质量门验收
```

- **triage**：四维归类（安全/可靠性/可维护性/测试）+ 每条 finding 的处置建议
  （auto_fixable / needs_test / needs_refactor / needs_decision / needs_review）+ 最有效的修复批次。
- **diff**：两层匹配——精确 id 相同算 existing；同 (source,rule,file,message) 但行号漂移算
  existing(moved)，不算 new/fixed，避免行号平移制造假警报。
- **gate**：目标 A = 0 blocker / 0 high / 0 复杂度 D-E-F / 覆盖率 ≥ 阈值 / 新增 blocker/high = 0；
  目标 B 放宽到 ≤2 high。工具有 error/timeout 时直接 exit 2（结果不完整不许当达标）。
  附带 local_rating（security/reliability/maintainability 的 A-E 本地近似口径，非 Sonar 官方评级）。
- **suppress**：确认误报/暂不修的 finding 走豁免，**必须写理由**，落 `<项目>/.cq/suppressions.json`
  （**本仓库就提交了这份文件**——2 条 deepsec 误报各带理由/时间/来源 run，豁免留痕可评审）。
  豁免带行号无关签名（source+rule+file+message）：全量格式化/大改后行号漂移不再失配；
  存量条目用 `cq suppress --reapply --run <新run>` 按签名对齐刷新。
  命中后 status=suppressed：不计入 gate/diff 判定，报告单列"已豁免"节。
- 基线文件在 `audits/baselines/<名字>.json`，自包含 findings，源 run 清理后仍可用。
- **fix**：分批修复计划，默认 dry-run（只出计划落 `fix-plan.json`，不改代码）。
  `--apply` 是用户显式批准的载体：必须配 `--batch N`（一次一批），且只对"自动修复"批次开放
  （ruff check --fix + ruff format）；安全/复杂度/测试类批次给人工指引，apply 会明确拒绝。
  apply 后不自动 commit，打印"跑测试 → 复扫 → diff → gate"闭环提示。

## Adapter 一览

| adapter | 工具 | 治什么 | 启用条件 |
|---|---|---|---|
| ruff-check | ruff check | lint、未使用导入、try-except-pass、blind except | 工具可用 |
| ruff-format | ruff format --check | 格式一致性 | 工具可用 |
| mypy | mypy | 类型错误 | 工具可用；有项目配置则完全尊重之 |
| radon | radon cc/mi | 圈复杂度（默认 D+）、可维护性指数（默认 C+） | 工具可用 |
| vulture | vulture | 死代码/未使用符号（默认 60% 置信度） | 工具可用 |
| pytest | pytest+pytest-cov | 失败测试、收集错误、覆盖率（默认阈值 80%） | 仓库有测试 |
| import-linter | lint-imports | 架构契约违约 | 仓库有 import-linter 配置 |
| deepsec | deepsec shield L1+L2 | 硬编码密钥、危险写法、注入（离线安全扫描） | pip 安装 或 `--deepsec-home` 源码仓库 |

## 产物

```
audits/<run_id>/
  summary.json    # 工具状态（版本/耗时/status/reason）+ totals + git/环境信息 + 配置快照
  findings.json   # 全部 findings（统一 schema，见下）
  report.md       # 人读报告：工具状态表、分级统计、明细、下一步建议
  raw/            # 各工具原始输出（已脱敏）
```

finding schema（与交接方案 §6 一致）：

```json
{
  "id": "sha1(source|rule|file|line|message)",
  "source": "deepsec|ruff|ruff-format|mypy|radon|vulture|pytest|import-linter",
  "category": "security|reliability|maintainability|test|architecture",
  "severity": "blocker|high|medium|low|info",
  "file": "src/foo.py", "line": 42,
  "message": "…", "rule": "…", "evidence": "…(脱敏)", "fix_hint": "…",
  "auto_fixable": false, "status": "new", "confidence": "high",
  "raw_ref": "raw/<tool>.json"
}
```

## 配置

默认值 < 仓库根 `cq.toml`（示例见 `config.example.toml`） < 环境变量（`CQ_PYTHON` / `CQ_DEEPSEC_HOME` / `CQ_DEEPSEC_PYTHON` / `CQ_TIMEOUT`） < 命令行。

## 测试与验收

- `python -m pytest tests`：核心、CLI、spec-drift 与 MCP 测试。MCP 测试需可选依赖；
  部分集成测试还需已有分析器、对应操作系统或显式故障/压力测试开关，跳过不计通过。
- 最新 A 门及平台测试计数见[验收记录](openspec/changes/archive/2026-10-26-add-local-cq-mcp/a-gate-validation.md)；
  真实宿主与发布矩阵分开记录，不用单测通过代替客户端验收。
- `tests/fixtures/demo-flask-api/`：故意埋了安全/类型/复杂度/死代码/格式/测试问题的 fixture 仓库，
  用于验收"六类问题一次全报出"。

## spec-drift（v0.2.0 · 可选）：spec 驱动项目的防漂移门

面向采用 spec 工作流（constitution → 现状规格 → 变更提案 → 实施）的项目，把"人记得维护 spec"
升级为"自动强制"。**默认关闭**：项目根放 `.specdrift.toml` 才启用，未配置的仓库 `scan/gate`
行为与旧版逐项一致（CI 有专项回归锁死）。

```toml
# .specdrift.toml（项目根）
code_paths   = ["app/", "prompts/"]   # 受 spec 管辖的代码路径
spec_root    = "openspec/specs"        # 现状规格根
change_root  = "openspec/changes"      # 变更提案根（proposal.md 含 spec_ref）
waiver_dir   = "decisions"             # 豁免归档目录
soft_timestamp_check = true            # 时间戳只做软提示
```

```bash
cq spec-gate --mode=hard              # 检查工作区改动（本地用法）
cq waiver --reason "先写代码，spec 周五前补齐" --ttl 48h   # 有期限豁免：decisions/ 生成文件 + 计入债务

# CI 门（v0.4.0）：干净 checkout 下用修订区间，否则工作区恒空、门恒绿
cq spec-gate --mode=hard --base origin/main        # 比对 <ref>...HEAD 的受管改动
cq spec-gate --mode=hard --range main...feature    # 显式区间（PR 场景）
```

- 区间感知（v0.5.0）：`--base/--range` 检查时，本次区间内被**归档**的变更（含 git mv）仍参与声明匹配——支持"实施→归档→推送"流程，且区间外旧归档不会永久白名单；无参时行为不变。
- 判定：变更粒度 delta 校验（活跃 proposal 的 `spec_ref` 指向存在的 spec 且含
  `ADDED/MODIFIED/REMOVED`，文本按词边界引用变更文件或显式目录形态 `app/`）；时间戳仅软提示。
- waiver 过期后 `spec-gate --mode=hard` 视为漂移并标红；账本复用 `.cq/suppressions.json`
  （条目带 `kind`，finding 与 waiver 互不干扰）。
- **v0.3.0 · 二期** ✅ `cq spec-rebuild`：AST 提取 `code_paths` 模块/公开符号 → spec 全文词边界匹配
  + spec 章节标题反向匹配，产出带置信度的**线索清单**（`code_missing` / `spec_missing` /
  覆盖率，`--json` 可机读）；`--draft` 只读（默认），`--apply` 落骨架模板（带 TODO 章节，
  不替人写内容）并清掉过期 spec 债。`cq promote`：decisions/ + 账本 waiver 按 slug/关键词
  聚类（重叠系数），`promote_window`/`promote_threshold` 可配（默认 30d/3），只输出候选与
  constitution 草稿，**永不写文件**。

## 路线图

- ~~**Phase 1**~~ ✅ `cq scan` + `cq doctor`：8 adapter 统一报告、环境体检、安装引导。
- ~~**Phase 2**~~ ✅ `cq triage` / `baseline` / `diff` / `gate` / `suppress`：基线对比、
  新增 blocker/high 即失败、local_rating 近似评级、带理由豁免机制。
- ~~**Phase 3**~~ ✅ `cq fix`（分批修复计划 + 显式 --apply）；DSH `SKILL.md`（已安装
  `~/.dsh/skills/ai-code-quality/`）+ Codex/Claude/Cursor 薄适配文件（见 `agent-adapters/`）。
- ~~**v0.2.0 · spec-drift 一期**~~ ✅ `cq spec-gate` + `cq waiver`（外部需求单驱动，含兼容性红线回归）。
- **本地 MCP 0.6.0rc1** ✅ PyPI/GitHub 公开预发布：九工具、异步任务、进程域/恢复、证据校验与分页；
  双宿主、A门和公开安装复验通过；[现状规格](openspec/specs/cq-mcp/spec.md)。
- **后续**：SonarCloud/SonarQube 接入、自研确定性 AI slop 规则、可选 AI review 与 toolkit 插件。
- **多语言（未排期）**：Java（Checkstyle/SpotBugs/PMD/JUnit+JaCoCo/ArchUnit adapter 集 + 语言探测
  + Java 符号提取）等，按真实需求立项；spec-gate/waiver/promote 已语言无关可直接用。
