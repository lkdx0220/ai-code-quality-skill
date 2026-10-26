# agent-adapters：薄适配层

核心思路：`cq` CLI 和可选 MCP 共用同一执行核心，不依赖特定 Agent 框架；
Skill 适配文件说明何时调用与如何解读，MCP 提供客户端可发现的工具接口。

| Agent | 适配文件 | 状态 |
|---|---|---|
| 任何 Agent（ZCode / Codex / 通用） | `generic/PROMPT.md` | ✅ Phase 1 交付 |
| DSH | `dsh/SKILL.md`（安装到 `~/.dsh/skills/ai-code-quality/`） | ✅ Phase 3 |
| Codex | `codex/AGENTS.md.snippet` | ✅ Phase 3 |
| Claude Code | `claude/CLAUDE.md.snippet` | ✅ Phase 3 |
| Cursor | `cursor/ai-code-quality.mdc` | ✅ Phase 3 |
| MCP 宿主 | `cq-mcp`（可选 `[mcp]` extra） | 已合入 main；Claude/Kimi 大结果、35秒响应等待与取消等定向验收通过；完整发布矩阵未关闭 |

新增一个 Agent = 新增一个 markdown 文件，cq 本体零改动。
适配文件只允许写"何时调、怎么调、如何汇报"，禁止复制 cq 的实现细节，避免多份说明各自漂移。
各文件的唯一详细版是 `generic/PROMPT.md`，其余文件只做触发与流程摘要并指向它。

配套 CLI 扩展见主 README 的“本地 MCP”章节：`scan --run-id`、
`--inputs-timeout-seconds`，`inputs --summary --timeout-seconds`，以及
`gate/diff --no-save`。输入清单不是分析器读取全集；选定 adapter 与完成 adapter
须区分，skipped 不作通过。MCP 启动与九工具调用见 [`docs/mcp.md`](../docs/mcp.md)；
旧v0.5.2标签不含MCP；源码安装与各宿主实际验收范围见主README和使用指南。

## 多 harness 环境的部署（SKILL.md 的安装点）

如果你的机器上有多个 Agent harness（多个 DSH home、Claude Code、Codex CLI），它们的 skills
目录相互独立，SKILL.md 需要同步到每一个。以四个常见位置为例：

| harness | 路径 |
|---|---|
| ZCode | `~/.zcode/skills/ai-code-quality/SKILL.md` |
| DSH（各 home） | `<每个 home>/skills/ai-code-quality/SKILL.md`；**实际主用 home 为 `~/.dsh-official`**（官方客户端，`launch-official-dsh.cmd` 启动） |
| Claude Code | `~/.claude/skills/ai-code-quality/SKILL.md` |
| Codex CLI | `~/.codex/skills/ai-code-quality/SKILL.md` |
| Trae（CN） | `~/.trae-cn/skills/ai-code-quality/SKILL.md` |
| WorkBuddy | `~/.workbuddy/skills/ai-code-quality/SKILL.md` |
| Kimi 桌面版（Daimon） | `%APPDATA%/kimi-desktop/daimon-share/daimon/skills/ai-code-quality/SKILL.md` |

同步命令（以仓库版为准）：

```bash
SRC="agent-adapters/dsh/SKILL.md"
for home in ~/.zcode ~/.dsh ~/.dsh-official ~/.claude ~/.codex ~/.trae-cn ~/.workbuddy; do
  mkdir -p "$home/skills/ai-code-quality" && cp "$SRC" "$home/skills/ai-code-quality/SKILL.md"
done
# Kimi 桌面版（Daimon）的 skills 在 AppData 下，单独同步：
mkdir -p "$APPDATA/kimi-desktop/daimon-share/daimon/skills/ai-code-quality" &&
  cp "$SRC" "$APPDATA/kimi-desktop/daimon-share/daimon/skills/ai-code-quality/SKILL.md"
```

注意：harness 一般在**会话启动时**扫描 skills，装完/更新后要新开会话才会生效。

**DSH 工具插件的安装位置同理分 home**：profile 级插件装在
`<home>/profiles/desktop/node_modules/`（junction 到插件目录）+ `package.json` 依赖 +
`dsh.profile.bundles` 数组 + `cordis.patch.yml` 条目，四件套缺一不可；
重启客户端触发装配。经验教训：装错 home 等于没装（两个客户端内核不同、home 隔离）。
