# 本地 cq MCP：变更提案（r03）

- change_id: `add-local-cq-mcp`
- 日期：2026-10-25（Asia/Shanghai）
- 状态：核心r03与服务候选已实现，九工具、任务/锁/进程域、证据判定、分页/状态容量及后续控制恢复修订均有阶段证据。最新源码A门exit0，Windows自扫452通过/12跳过，见a-gate-validation.md；两个真实宿主的大结果/35秒延迟等待/取消及不同断开场景见host-acceptance-ab3d484.md。尚不表示全矩阵验收；未发布，本候选无新增独立签署。
- spec_ref: `openspec/changes/add-local-cq-mcp/specs/cq-mcp/spec.md`
- 主仓：ai-code-quality；参考：dsh-ai-code-quality-lab/dsh-plugin（只读）。
- 来源基线：source-baseline.json；主仓 HEAD `252ec3cf5bd3ca3024ab8dc0ee7111f6573ccad7`。

## 为什么做

cq 已有 CLI、Skill 和 DSH 插件。MCP 让支持该协议的客户端发现扫描能力、管理长任务并复用可信结果；使用者在自己电脑安装运行，作者不承担扫描托管。Skill 保留工作流，核心保留检测和评级算法，MCP 负责协议、生命周期与证据约束。不能把接入协议说成新增检测算法，也不能把本地近似评级称为 Sonar 官方评级。

## 开工前现状核查

1. 核心版本0.5.2、Python>=3.11、dependencies=[]，现有入口cq。开始本变更时无OpenSpec目录；未发现适用AGENTS.md及.specdrift.toml。
2. CI专门验证无.specdrift.toml的兼容性，本变更不自动启用它。参考DSH插件0.1.1不是第二核心来源。
3. 现scan使用秒级ID和exist_ok=True；没有最终完成标记；summary.scanned_targets只有入口路径，并非逐文件指纹。
4. 现gate/diff会写run目录；load_baseline支持run回退但优先同名具名baseline。工具error/timeout产生gate exit2，coverage/baseline缺失可skipped而不失败。
5. Config.snapshot缺effective adapter选择所需部分字段；显式空adapter可能回退全量；doctor未正确传python_source。
6. pytest及分析器配置/插件可能执行项目代码，MCP只面向可信项目，不是操作系统沙箱。

## 首版范围

- 同仓可选MCP extra与cq-mcp入口；本地stdio，单项目绑定，CLI零运行时依赖保持。
- 九工具：cq_doctor、cq_scan_start、cq_job_get、cq_job_cancel、cq_runs_list、cq_findings_get、cq_diff、cq_gate、cq_artifact_get。
- doctor/scan均为可取消、有总期限的应用层job；初始化不探测解释器/分析器；不依赖实验性MCP Tasks。
- scan scope固定full；默认ruff-check/ruff-format/mypy/radon/vulture五项，import-linter/deepsec显式选择，pytest另须启动允许；未选维度完整披露，核心也拒绝显式空列表。
- SQLite事务去重、用户目录OS咨询锁、进程域和崩溃恢复；同OS用户/固定锁命名空间内跨state互斥，不保证跨用户或直接CLI串行；Linux强杀后不能确认残留清理时阻断。
- 核心共享输入监视清单和完成标记，区分范围排除、运行缺口、历史结果与当前验证；监视集合不是分析器实际读取全集。
- verdict取代旧assessment；质量失败是有效领域结果，不映射为调用错误。默认范围排除与选定工具执行失败分开；显式不验证当前时可给pass_historical，校验超时则cannot_judge，不能冒称当前通过。inputs期限可配1..600s。
- gate/diff以--no-save调用，stdout快照由state管理；完整捕获上限8MiB，协议返回总上限64KiB，大结果分页/分块，超硬限明确回退。
- Windows/Linux、wheel/sdist干净安装、两个真实客户端验收仍为发布条件。

## 首版排除

HTTP托管、多人租户、远程认证计费；自动安装分析器；自动修代码/commit/push；MCP新增或重写suppression/waiver/baseline；spec-rebuild apply；全量搬运DSH工具；改变检测规则、严重度和门阈值；保证恶意项目隔离或检测所有秘密。已有CLI写能力继续通过原入口使用。

## ADDED

CQ-MCP-01至CQ-MCP-15定义于specs/cq-mcp/spec.md，design.md为规范性字段/算法补充，tasks.md列28组验收。

| 计划路径（施工状态见tasks.md） | 用途 |
|---|---|
| src/ai_code_quality/mcp/ | stdio、schema、job/锁/进程域、证据、分页、CLI薄适配 |
| tests/mcp/ | 协议、并发、权限、异常恢复、证据及兼容性测试 |
| tests/fixtures/mcp/ | 无凭据确定性夹具及异常子进程 |
| docs/mcp.md | 安装/启动、可信边界、写入范围、终态重试和清理指引 |
| docs/releases/cq-mcp/ | 平台/客户端矩阵及发布证据 |
| examples/mcp/ | 不含私人路径/凭据的配置示例 |

## MODIFIED

r02核心扩展比r01多，已显式列入范围；不能继续称为“只加run-id”。新建其他核心模块前须同步此表。

| 路径 | 拟定变化 |
|---|---|
| pyproject.toml | 可选extra、cq-mcp入口、SDK/打包声明 |
| src/ai_code_quality/__init__.py | 发布准备时统一版本，尚不指定新版本号 |
| src/ai_code_quality/scan.py | 参数先验证、显式run ID、独占目录、配置/输入摘要、原子证据发布及.complete.json |
| src/ai_code_quality/cli.py | scan --run-id/--inputs-timeout-seconds；inputs --summary/--timeout-seconds；gate/diff --no-save；新错误/退出码及doctor来源 |
| src/ai_code_quality/config.py | snapshot纯增enabled_adapters/no_deepsec/respect_gitignore |
| src/ai_code_quality/targets.py | 共享监视枚举、规则版本、配置与源/测试摘要，不改变旧扫描目标选择 |
| src/ai_code_quality/evidence.py（新增） | 标准库证据原子写入、run ID/路径校验、完成标记与摘要核验，供核心和MCP共用 |
| src/ai_code_quality/runs.py | marker/inputs/schema任一指示新格式即校验完成标记；防schema降级、路径越界、UTF-8损坏及大小写误判；旧合法run保持兼容 |
| src/ai_code_quality/baseline.py | 审核r02补齐具名基线读写归属、形状/解码校验、原子保存；不重写历史基线或增加可比性背书 |
| src/ai_code_quality/report.py | 控制台与diff展示在完整输出边界统一脱敏 |
| src/ai_code_quality/gate.py | 仅修正tools_ok统计说明与控制台脱敏；不改变评级、检查谓词、阈值或退出码 |
| src/ai_code_quality/adapters/__init__.py | None保留默认；显式空列表拒绝 |
| src/ai_code_quality/redact.py | 版本化已知规则补Authorization/Bearer |
| tests/test_scan_paths.py、tests/test_cli_commands.py、tests/mcp/ | 核心兼容及新契约回归；新增测试文件先同步路径 |
| .github/workflows/ci.yml | 可选依赖、跨平台协议/打包验证，保留无配置兼容检查 |
| README.md、agent-adapters/README.md | 九工具、写入范围、边界与回退；不改用户已安装Skill |

gate.py、diff.py的评级/差量算法不在改写范围；gate.py本轮只允许统计说明与输出脱敏。schema.py暂不改；runs.py依据marker/inputs/schema联合识别新格式，不能靠降级版本字段跳过核验；旧合法run读取兼容。Config来源跟踪按显式选择记录，即使显式解释器恰等于默认路径，也不能误记default而触发自动切换。不改DSH参考副本。

## 可见行为变化

默认时间戳run命名保留，但同秒碰撞由隐式复用改为RUN_COLLISION/exit3；显式空adapter由可能全量执行改为拒绝。两者均须发布说明和负控。新scan产物schema2含完成标记；旧run只作未验证历史展示，不自动升级。Config.snapshot加字段，CLI正常输出保留；--no-save仅新调用选择，原CLI仍默认保存。产物IO失败exit4，scan1及gate/diff3等旧映射见design。锁写用户目录，不新增项目根锁文件；逻辑容量为256MiB总额/独立计数上限和瞬态预留，达到任一即拒新操作。MCP尚未发布，r03的envelope1.2和pass_historical无已发布客户端迁移承诺。

## 发布完成的定义

本轮审核修订另含这些可见变化：inputs规则v2先脱敏展示路径，保留path_sha256区分身份，摘要纳入脱敏规则版本；规则不同不可直接比较。summary显式区分selected/attempted/completed/skipped，effective_adapters保留选定范围别名。新格式读取fail-closed；引用仅单级ID/前缀，Windows按实际名称校验；半写exact目录为RUN_NOT_READY。gate/diff保存使用紧凑排序键LF JSON并脱敏；POSIX原子产物默认0600。coverage仅在发布阶段保留适配器处理后的字节，适配器自身仍做文本转换/脱敏；没有目录fsync/断电事务承诺。具名基线归属/形状/原子保存及异常文件名错误归类见design。

完成tasks全部必验并记录真实版本/失败轮/未执行项，缺任一必验保持候选。实际SDK版本、第二宿主及Windows进程控制先调查，不将假设写成已支持。可由固定Git tag分发，不假定已有PyPI凭据。实现、候选验收与对外发布分别记录，发布渠道和具体候选交用户确认。

## 本分支的审查安排

本分支只负责项目补强。用户转交DeepSeek和GLM的r02复核，两者结论均“可实施”。r03落实复核N项，处理记录见reviews/independent-review-r03-disposition.md；不冒称r03获独立签署，也不把静态认可当运行验收。实施前调查/隔离原型可推进，核心扩展需以本稿决定和原型结果为依据；不再机械增加一轮整包审核前置。旧材料/意见保留，不引入其他项目专责流程。核心首批实施与失败轮见core-implementation.md；未调用外部模型、未commit或发布。
