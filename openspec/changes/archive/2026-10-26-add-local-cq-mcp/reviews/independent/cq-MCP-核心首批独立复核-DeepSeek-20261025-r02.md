# cq MCP 核心首批（r02）独立复核（DeepSeek）

- 审核对象：`C:/Users/24701/Desktop/skills开发/cq-MCP-核心首批实施与证据-20261025-r02.zip`
- 固定旧基线：`252ec3cf5bd3ca3024ab8dc0ee7111f6573ccad7`
- 审核日期：2026-10-25（Asia/Shanghai），本报告写于 15:0x
- 审核范围：manifest 指定的 12 个候选文件、其直接调用链、旧 run/基线读取链、发布/校验/脱敏/CLI 映射；MCP 九工具、SQLite、锁、进程域、verdict、分页、宿主与发布矩阵不在本批实现，未当作本批缺陷
- 环境：`C:\Users\24701\AppData\Local\Programs\Python\Python313\python.exe`（Python 3.13.14，MSC v.1944 64bit，Windows 11 10.0.26300）；测试解释器 **未安装 mcp 包**（`find_spec("mcp") is None`）；pytest 可用；ruff/mypy/radon/vulture 可用
- 独占地：`C:/Users/24701/Desktop/skills开发/deepseek-audit-core-r02-20261025/`（新建，未覆盖任何既有文件；主仓、正式 `.cq`、冻结 ZIP、旧证据、规格均只读访问）
- 独立性：第一遍只读 proposal/design/spec/候选源码与调用链；第二遍才读 `core-review-fixes.md`、`reviews/core-r01-disposition.md` 及 `review-inputs/` 两份 r01 审核。**未读取** `reviews/glm-r03.md`、`reviews/deepseek-r02.md`、`reviews/adjudication.md`、`reviews/independent-review-r02-disposition.md`、`reviews/independent-review-r03-disposition.md`；未调用其他模型。
- 补读范围：固定 HEAD 的 `gate.py`、`diff.py`、`baseline.py`、`report.py`、`schema.py`、`suppress.py`、`doctor.py`、`runner.py`、`adapters/*.py`、`tests/`，以及候选 `targets/scan/cli/runs/evidence/redact/config` 全量；未读主仓 `audits/` 下的正式历史证据（只读包内证据）。
- 本文件是实现审查，不是产品发布验收；不构成对 MCP 方案、双宿主、打包安装或跨平台承诺的通过。

## 0. 结论

**修复列明问题后可进入 MCP 服务层。**

正面依据：上一轮最关键的证据链缺陷（单字段改 schema 关闭校验）已被真正修好，且我按“schema 值 × marker 存在 × inputs 存在”的组合逐格攻击，除真正的 legacy 形态外全部 fail-closed；run/audits 的读取归属、大小写别名、二进制产物损坏、inputs v2 的“脱敏后路径 + path_sha256 + 内容摘要 + 规则版本”可复算性，均经独立实跑成立；`--no-save`、adapter 选择/尝试/完成/跳过语义、gate/diff 算法未改、正式 `.cq` 未改也成立。

不同意作者“未发现剩余进入服务层阻断项”的结论。仍有 4 条 P2 落在 MCP 将实际消费的路径上，其中两条会以裸 traceback/业务 exit1 出现：

1. **基线读取链**：`audits/baselines` junction 可读到项目外基线并参与 gate/diff 判定；基线 JSON 形状损坏会裸 traceback + exit1（不是 INVALID_ARTIFACT，且 exit1 与 gate 的“质量失败”同码）。
2. **非 UTF-8 文件名**：Windows 允许孤立代理字符文件名；`cq inputs` 裸 traceback，`cq scan` 误标 INVALID_ARGUMENT/exit1 并留下无标记半写目录。这是 r02 新增代码路径引入的问题。
3. **脱敏通道归属**：默认 `scan`（md）把工具 `reason` 原样打到 stdout，已知凭据形态可泄露；`gate/diff` 对 legacy findings 的 stdout 也未过规则。JSON/产物路径已修好，但“所有输出经版本化规则”的表述不成立，核心与 MCP 之间仍有归属空档。
4. **selected 但 skipped**：核心 gate 把 skipped 当“全部正常完成”，全 skipped 的 run 可 gate exit0/passed=true；MCP 必须自己按 evidence 判 cannot_judge，不能在契约里把 core_gate 当最终通过。

另外两条必须纠正的声明（不阻断，但不能作为保证引用）：coverage “分析器原字节、不经文本重写”在生产者侧不成立（作者测试绕过了真实 adapter）；“保留正常 bearer 英文行文”只覆盖小写短词，`Bearer authentication` 仍被误脱敏。

没有发现 P0/P1。

---

## 1. 发现（P0/P1/P2/P3）

> 编号说明：本报告的新发现用 P2-1…/P3-1…；旧审核项沿用其原编号（DS … / GLM …）。第 2 节表格中凡指本报告新发现处写“本报告 Px-y”。

> P0/P1 定义：能让未发布/被篡改证据在已启用校验的路径上被当作合法结果，或直接使本批证据链不可用。P2：MCP 服务层实际消费的核心路径上的可复现错误，进入服务层前必须修复或在 MCP 契约中显式承担并测试。P3：可后移/需纠正声明/已披露边界。

### P0

无。

### P1

无。schema 单字段绕过已修复；run/audits 归属、完成标记、五类依赖摘要、二进制损坏均 fail-closed。

### P2-1 基线读取链：项目外基线可参与判定；baseline JSON 形状损坏裸 traceback + exit1

**位置（均为 HEAD 未改文件，但属 r02 声称的读取防线）**

- `src/ai_code_quality/baseline.py:41-68`（`load_baseline`）；`:48` `baseline_path`；`:49` `path.is_file()`；`:51` `json.loads`；`:54` `data.get(...)`；`:59` `findings`；`:67` 回退 `load_run`。
- 消费方：`gate.py:113-116`、`cli.py:580-585`（diff）、`cli.py:646-657`（gate）。
- `diff.py:62`、`gate.py:134-137` 对 finding 调 `.get`。

**触发与实测**

1. 越界读取：项目 `C/` 的 `audits/baselines` 用 `cmd /c mklink /J` 指向项目外 `C-outside`，外置 `evilbase.json` 含 `source_run_id=runC` 与一条 blocker。执行
   `diff --project C --run runC --baseline evilbase --format json --no-save`
   → **exit 0**，`baseline_run="evilbase(←runC)"`，`fixed=1`，`fixed_details` 来自外置文件。子进程 PID 21868，0.076 s，见 `logs/repro_pids.json`、`logs/probe2.json`（kind=baseline_junction）。
   对照：同一项目 `--baseline no-such-base` → exit 3 RUN_NOT_FOUND，说明确实读了外置文件而不是回退 run。
2. 形状损坏：
   - `audits/baselines/badlist.json` 内容 `[]` → `gate --baseline badlist`：**exit 1 + 裸 traceback**，`AttributeError: 'list' object has no attribute 'get'` at `baseline.py:54`；PID 41992，0.087 s。
   - `{"source_run_id":"runA","findings":[1,2]}` → `diff --baseline baditems`：**exit 1 + 裸 traceback**，`AttributeError: 'int' object has no attribute 'get'` at `diff.py:62`；PID 41452，0.085 s。
   - `{"findings": {"oops": ...}}`（非数组）→ 被静默当空列表（diff new=1，无报错），见 P3-3。

**预期 / 实际**

- 预期：基线文件按 `audits/baselines` 真实归属校验；非对象/坏 items → `INVALID_ARTIFACT`（经 `RunNotFoundError`）→ gate/diff exit 3、JSON error envelope；不得裸 traceback。
- 实际：越界 junction 可读；坏 JSON 形状 → 裸 traceback、exit 1。exit 1 与 gate 的“质量失败”同码、与 diff 的“有新增 blocker/high”同码，MCP 若先看 exit 再解析 JSON，存在把“产物损坏”当“领域失败”的歧义。

**影响**

- 这是 MCP `cq_gate`/`cq_diff` 的 `base_run_id` 读取路径；baseline JSON 是自包含产物，`save_baseline` 又是非原子写入（P3-3），崩溃/手改后可稳定触发。
- 与 r01 P2-2（run 读取越界）同类；核心对 `audits` 根和 run 目录做了 `inside()`，却漏了 `audits/baselines/<name>.json`。MCP 若不复核，会把项目外基线当本项目历史基线；若不复核 JSON，会把 traceback/exit1 当业务结果。
- 文件级 symlink 未能在本机创建（SeCreateSymbolicLinkPrivilege 拒绝，WinError 1314），但该分支与目录 junction 共用同一条“直接 `path.is_file()` + `json.loads`、无 `inside()`”的代码路径；POSIX 文件 symlink 属静态推断的同类入口，未实跑。

**最小修正**

- `load_baseline`：`path = inside(baseline_path(...), audits_dir(project))`；`data` 必须 dict，`findings` 必须 list[dict]，否则 `RunNotFoundError(..., "INVALID_ARTIFACT")`；捕获 `AttributeError/TypeError/ValueError` 并归一。
- 或在 MCP 层强制：基线文件 realpath 必须在 `audits/baselines` 下、JSON 必须过 schema、exit1 必须伴随合法报告才接受。

**服务层前是否必须**：**是**（核心修或 MCP 契约+测试二选一；不能两层都假设对方做）。

---

### P2-2 非 UTF-8 文件名：`cq inputs` 裸 traceback，`cq scan` 误标 INVALID_ARGUMENT/exit1 并留下无标记半写目录（r02 新增路径）

**位置**

- `src/ai_code_quality/targets.py:169-178`，关键 `:172-174`：`path.relative_to(root).as_posix().encode("utf-8")`。
- `src/ai_code_quality/cli.py:843-846`（inputs 只捕 `EvidenceError`/`OSError`）；`:801-808`（scan 捕 `ValueError`，无 `.code` → exit 1）。
- `src/ai_code_quality/scan.py:74-86`（先建 `audits/<run>/raw`，再 `monitor_inputs`）。

**触发与实测**

- Windows 允许孤立代理字符文件名：创建 `bad\ud800name.py`（`os.listdir` 返回 `'bad\ud800name.py'`）。
- `inputs --project G --summary --format json` → **exit 1 + 裸 traceback**：`UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' ... surrogates not allowed` at `targets.py:173`；PID 46860（早期）与 PID 46076（新建 `fixtures/surrogate-fresh`，`logs/surrogate_fresh.json`），0.08 s。
- `scan --project G --adapters ruff-check --run-id fresh1 --format json` → `{"error":{"code":"INVALID_ARGUMENT",...}}`、**exit 1**（PID 45336，0.084 s）；`audits/fresh1/` 已创建，仅 `raw/` 一个空目录、0 文件、无 `.complete.json`。按设计，这应是 `INPUTS_UNAVAILABLE`（exit 2）或结构化证据错误，不是“参数非法/exit 1”。

**预期 / 实际**

- 预期：文件名不可 UTF-8 编码属于“输入不可用”，应归一为 `INPUTS_UNAVAILABLE`（inputs exit 2 / scan exit 2、无 marker），或采用可逆转义/`surrogatepass` 保留身份；`inputs` 也必须走 JSON error envelope。
- 实际：裸 traceback / 误分类；scan 留下空半写目录，之后同 ID 重试得 RUN_COLLISION，exact 读取得 RUN_NOT_READY（fail-closed，但失败原因不可诊断）。

**影响**

- `cq inputs --summary` 是 MCP 的 freshness 原语；一个合法但文件名畸形的项目会让核心崩溃而不是给出“无法完成监视”的结构化结论。MCP 只能映射为 INVALID_OUTPUT/CLI_ERROR，违反“inputs 失败 → INPUTS_TIMEOUT/UNAVAILABLE”的契约。
- 这是 r02 新代码 `monitor_inputs` 引入的回归（HEAD 没有该路径）。

**最小修正**

- `monitor_inputs` 内 `except UnicodeError` → `EvidenceError("INPUTS_UNAVAILABLE", ...)`；或 `encode("utf-8", "surrogatepass")` 后仍以 `path_sha256` 区分身份，展示路径用转义表示。
- `_run_inputs_command` 增加 `except ValueError` → `_command_error(..., "INVALID_ARGUMENT"/"INPUTS_UNAVAILABLE", ...)`；`_run_scan_command` 对 `UnicodeError` 映射 exit 2 而非 1。
- 加负控：代理字符文件名。

**服务层前是否必须**：**是**（inputs/scan 都将是 MCP 调用面；且属新代码回归）。

---

### P2-3 脱敏通道归属：md 控制台 `reason` 未脱敏；gate/diff 对 legacy findings 的输出未脱敏

**位置**

- `src/ai_code_quality/report.py:183-205`（`build_console_output`），`:190` 直接 `f"（{t.get('reason')}）"`，无 `redact_text`。
- `src/ai_code_quality/cli.py:849-863`（`_print_scan_console`）。
- 生产者把原始输出尾段放进 `reason`：`adapters/pytest_cov.py:113-121`（`tail = (stderr+stdout) 最后 3 行`）；其他 adapter 同类。
- gate/diff：`cli.py:668-674` 直接 `json.dumps(report.to_dict())`，`cli.py:614-615` 直接 `json.dumps(payload)`，没有 `redact_obj`；legacy run 的 findings 是历史原始文本。

**触发与实测**

1. 真实端到端（默认 md 控制台）：项目 `E/pytest.ini` 写入 `addopts = --sk-proj-ffff…`（假凭据形态，非真实 secret），`scan --project E --adapters pytest --run-id pidcheck`（不指定 `--format json`）→ exit 2，stdout 直接含 `--sk-proj-ffffffffffffffffffffffffffffffff` 原文；同次 `summary.json` 中该 token 已被替换为 `--***REDACTED***`。PID 44332，1.586 s（`logs/repro_pids.json`、`logs/probe3.json` kind=leak）。
2. 函数级最小复现：`build_console_output` 的 `tools[0].reason` 含 `Authorization: Bearer sk-proj-…` → 输出原样保留（`logs/probe3.json` kind=leak console reason）。
3. legacy gate：构造无 marker、findings 含同一假 token 的旧 run，`gate --format json --no-save` → stdout 含 token（`logs/probe6.json` kind=leak_legacy，gate_has=true）；`diff` 在同一 run 作基线时 new=0，未暴露该字段，但换基线后 `new_details` 会带 message。

**预期 / 实际**

- 预期：按 design §6/§9“所有输出经版本化规则”“成功 scan JSON 同样脱敏”的口径，控制台、gate/diff stdout、快照都应过规则；至少核心与 MCP 必须有一层明确承担并测试。
- 实际：JSON scan/inputs/summary/findings/report.md/inputs.json 已脱敏（我实测已知形态不落盘、不出现在 JSON stdout/error）；但 md 控制台 `reason`、legacy gate stdout 未脱敏。

**影响**

- 默认 CLI 是用户可见/可粘贴的公开通道；工具诊断里的已知凭据会泄露。MCP 走 JSON 路径，schema2 run 的 findings 已在 scan 时脱敏，所以 MCP 主路径不受 (1) 影响；但 (3) 说明“core stdout 即脱敏快照”这一假设不成立，MCP 的 `gate_result/diff_result` 快照必须自己再过规则；否则 legacy/外部 run 可泄露。
- 这也纠正 r01 报告“md 控制台已脱敏”的误判（该结论当时未实测 reason 通道）。

**最小修正**

- `build_console_output` 返回前 `redact_text`（或对 `reason` 单独处理）；`_print_scan_console` 的 stderr 文案同样。
- gate/diff 的 `to_dict()`/payload 在打印/保存前 `redact_obj`，或 MCP 契约明确“核心 stdout 未脱敏，MCP 必须对全部快照过 REDACTION_RULES_VERSION 并落测试”。
- 加两条负控：md 控制台 reason、legacy gate stdout。

**服务层前是否必须**：**是（归属必须明确）**。若 MCP 承诺所有返回/快照脱敏，则实现该层并测试；核心 md 通道建议一并修（成本一行级）。

---

### P2-4 selected 但 skipped：核心 gate 当作“全部正常完成”，全 skipped 可 exit0/passed

**位置**

- `src/ai_code_quality/gate.py:121-131`：`has_tool_errors()` 只看 `error/timeout`；`tools_ok` 用 `len(tools)` 计数，skipped 也算“正常完成”。
- `runs.py:50-52`（`has_tool_errors`）同样只看 error/timeout。
- 新 summary 已正确提供 `selected/attempted/completed/skipped`（`scan.py:137-145`），但 gate 未消费。

**触发与实测**

1. 全 skipped：项目无 tests，`scan --adapters pytest --run-id skip-gate-check-2`（pytest 显式选中、adapter 返回 skipped）→ exit 0；随后 `gate --run skip-gate-check-2 --format json --no-save` → **exit 0、passed=true**，`tools_ok.detail="1 个工具全部正常完成"`；coverage/new_blocker_high 均 skipped。PID：scan 43100、gate 37664（`logs/skip_gate.json`）。
2. 最终 run 04：`tools` 中 import-linter 为 skipped，但 gate 的 `tools_ok.detail` 仍是 **“8 个工具全部正常完成”**（`logs/gateA.full.json`）。
3. 真实 timeout：`scan --adapters pytest --timeout 1` 的 run，gate exit 2、tools_ok=false（PID 41968，`logs/misc_verify.json`、`logs/probe5.json`）。

**预期 / 实际**

- 预期（CQ-MCP-08/design §4 第 3 步）：显式选中但 skipped 是 runtime gap → `cannot_judge`；不能当完成，也不能当“范围外”。
- 实际：summary 层正确区分（这点已修好）；core gate 层仍把 skipped 当完成并给出 pass。MCP 若把 `core_gate.passed/exit0` 当最终 verdict，会出现零执行工具的质量通过；若按设计自己算 verdict，则必须显式忽略 `core_gate.passed` 并用 `skipped_adapters` 判 cannot_judge（且返回的 `core_gate` 里仍有误导字段）。

**影响**

- 这是“完整证据与质量通过不可混淆”的直接冲突点；MCP 的 evidence/verdict 必须独立实现，不能复用 core gate 的 passed。author 的最终 A 门证据因此含一处事实错误文案（import-linter 明明 skipped）。

**最小修正**

- MCP：`selected - completed`（含 skipped/error/timeout/missing）全部进 runtime_gaps → cannot_judge；测试全 skipped、部分 skipped、显式禁用。
- 核心（可选，但建议）：`tools_ok` 把“selected 但 skipped”列为 gap；或至少把 detail 改为“7 ok / 1 skipped”，不写“全部正常完成”。若坚持“gate 算法不改”，须在 MCP 契约和文档写明 core_gate 不能单独作最终 verdict。

**服务层前是否必须**：**是**（作为 MCP 契约与测试；核心改动可后移，但不得把 core_gate 当最终通过）。

---

### P3（可后移或必须纠正声明）

**P3-1 coverage “分析器原字节、不经文本重写”在生产者侧不成立；新测试绕过了真实 adapter**

- `adapters/pytest_cov.py:247-248`：`cov_text = cov_json.read_text(encoding="utf-8", errors="replace")` → `write_raw(ctx, "coverage.json", cov_text)`；`adapters/base.py:89` 再 `redact_text` + `write_text`。`scan.py:119-122` 只 `sync_file`，不重写；`evidence.sync_file` 只 fsync。
- 实跑 `PytestCovAdapter._coverage_section`（真实方法、真实文件）：
  - CRLF 合法 JSON → 逐字节不变（85/85，3 CRLF/3 CRLF）；
  - LF-only 合法 JSON → **82 → 85 字节，0 → 3 CRLF**；
  - 非法 UTF-8 字节 → **104 → 110 字节**（替换字符 + 换行转换）；
  - 含 `sk-proj-…` 路径的 JSON → **146 → 124 字节**（被脱敏，内容改变）。
  见 `logs/probe4.json` kind=coverage_bytes。
- 真实 coverage.py 输出是单行 LF JSON（最终 run 179,647 字节、0 LF/0 CRLF），所以该实例字节未变；但只要覆盖配置输出多行、路径含已知凭据形态或非 UTF-8，字节即变。作者测试 `test_coverage_publication_preserves_exact_analyzer_bytes` 用假 adapter 直接 `write_bytes`，没有经过上述真实生产者路径，因此不能证明“分析器原字节”。
- 影响：marker 摘要的是“被 adapter 重写后的字节”，不是分析器原始字节；“不经文本换行重写”的声明不成立。对 gate 的覆盖率解析通常无害，但对外部复算/证据信任是错的。
- 修正：adapter 改为字节级复制/原地 fsync（或明确“coverage 经已知规则脱敏，bytes 非原字节”并改测试）；补真实 adapter 负控。服务层前非必须，但声明必须纠正。

**P3-2 正常 bearer 英文行文仍被误脱敏（大写 + 8 字符以上）**

- `redact.py:24`：`(\bBearer\s+)[A-Za-z0-9._~+/=-]{8,}`，IGNORECASE。
- 实测：`"Bearer authentication is required"` → `"Bearer ***REDACTED*** is required"`；`"please send bearer credentials..."` → 同样被替换；`"the bearer of bad news"` 不变（小写 + 短词）。
- 作者回归只测了小写短词（`test_bearer_prose_is_not_a_token`），未覆盖大写/长英文词；“保留正常 bearer 英文行文”的声明只部分成立。
- 方向是多脱不漏（安全），不泄密；但会破坏报告可读性/MCP artifact 文本。修正：要求 token-like 字符集/长度下限更高，或仅在 header 上下文脱敏；补大写行文反例。服务层前非必须。

**P3-3 baseline CLI 的写侧/边界（非 MCP 工具，但属核心读取链的上游）**

- `baseline.py:23-38` `save_baseline` 用 `path.write_text`（非原子、无 fsync）；崩溃可留下坏 JSON，直接触发 P2-1。
- `--name CON` / `NUL`：exit 0 并打印“基线已保存：…\baselines\CON.json”，但磁盘上**没有**该文件（Windows 设备名）；是静默假成功（`logs/probe2.json` kind=baseline_name）。
- `--name` 300 字符：`OSError: [Errno 22] Invalid argument` 裸 traceback、exit 1（`logs/probe2.json`）。
- `audits/baselines` 为指向项目外的 junction 时，`baseline --name escape` 在项目外创建 `escape.json`，exit 0（`logs/probe6.json` kind=baseline_write_junction）；写侧同样没有 `inside()`。
- `load_baseline` 把 `findings` 非数组静默当空（`logs/probe6.json` kind=baseline_shape_silent，diff new=1，无报错）。
- 修正：baseline 名加长度/设备名限制、写前 `inside`、原子写、`findings` 类型校验。MCP 不开放 baseline 写，故非服务层阻断。

**P3-4 具名 baseline 的 payload 不足以单独建立 MCP 可比性**（静态推断）

- `save_baseline` 只写 `name/source_run_id/created_at/git/totals/findings`（`baseline.py:29-37`），没有 scope、有效 config、rules/tool 版本、inputs digest、publication。
- CQ-MCP-10 要求比较 scope/规则/工具版本/配置/suppression；仅凭 baseline 文件无法判定“两侧均已验证/同策略”。MCP 必须解析 `source_run_id` 重新加载源 run 并校验 publication/config；源 run 已清理时只能 `comparable=false`。
- 这不是核心缺陷（设计说“基线只验证历史产物身份”），但服务层必须显式承担，不能只看 baseline payload 就判可比。

**P3-5 `.gitignore` 子集：相对目录/带斜杠通配不生效；本仓被忽略的 6 个夹具 .py 仍在监视集合**

- `targets.py:208-265`：`dir/` 只支持单段目录名；`sub/dir/` 被塞进 `dir_names` 后按单段比较，永不命中；`sub/*.py` 被当 exact rel_path，永不命中；exact `sub/dir/x.py` 生效。
- 实测：`ignored/` → 排除；`sub/dir/`、`sub/*.py` → **不排除**（`fixtures/probe9`）。
- 本仓 `.gitignore` 用 `tests/fixtures/demo-flask-api/`，git 忽略，但 `monitor_inputs(主仓)` 仍纳入 6 个 `.py`（63 vs 候选树 57）；最终 run 的 inputs 含这 6 个文件。设计已声明“root-only gitignore 子集”，但未点明“相对目录/带斜杠 glob 不支持”；`respect_gitignore=True` 的语义容易被误解。
- 修正/披露：支持相对目录前缀，或文档逐条列支持形态并加 fixture；服务层前非必须（不破坏一致性，但影响范围声明）。

**P3-6 前缀解析遇任何越界 junction 会整体失败（fail-closed 但过粗）**

- `runs.py:74-80` 在生成器里对每个匹配目录 `inside(d, root)`；`audits/aaa-evil` 指向项目外时，`load_run(project, "a")`（前缀）→ **OUTSIDE_PROJECT**，而 exact `alpha` 仍可读（`logs/probe6.json` kind=prefix_junction）。
- 影响：一个杂散链接可让所有前缀引用不可用；不是逃逸，是可用性/诊断问题。修正：逐个跳过/标记坏条目，只在身份被选中时拒绝；或先校验一次 audits 根。

**P3-7 `summary.json` 为目录 → IO_ERROR/exit4，而非 INVALID_ARTIFACT**

- `runs.py:92-95` 先 `exists()` 再 `read_text`；目录 exists=true → `IsADirectoryError`（OSError，非 FileNotFound）→ `IO_ERROR` exit4（`logs/probe6.json` kind=summary_dir）。
- 与“产物损坏归 INVALID_ARTIFACT”不完全一致；属分类细节，不产生 traceback。修正：先 `is_file()` 或把 IsADirectoryError 归 INVALID_ARTIFACT。

**P3-8 `publish_run` 把“非文件”的 coverage 当 absent**（静态推断）

- `evidence.py:105-108`：`if not path.is_file() and name == "raw/coverage.json": files[name]={"absent": True}`；若 adapter 在 raw 下创建了名为 `coverage.json` 的目录，scan 会发布“absent”marker，而随后的 verify 看到 `path.exists()` 为 true → INVALID_ARTIFACT（自相矛盾）。当前 raw 新建、pytest 写文件，现实触发面窄；修正为 `if not path.exists()`，并对目录显式报错。

**P3-9 scan 在输入监视前就建 run/raw，输入失败留下空半写目录（r02 顺序变化）**

- `scan.py:74-86` 先 `audits/<id>`、`raw/`，再 `monitor_inputs`；真实 `--inputs-timeout-seconds 0.000001` → exit 2 INPUTS_TIMEOUT，`audits/to/` 存在但 **0 文件、无 marker**（`logs/probe5.json` kind=inputs_timeout_scan）。
- fail-closed（不会被当合法），exact 读取 RUN_NOT_READY；但同 ID 重试被 RUN_COLLISION 阻塞，且目录不是“失败证据”。设计允许保留失败轮目录，但空目录没有诊断价值；可考虑先监视再建目录，或写入 failure.json 并明确语义。

**P3-10 旧 run 名含点/空格/超 128 字符将不可读（新的兼容收紧，静态推断）**

- `resolve_run_dir` 现在先 `validate_id`；HEAD 接受任意目录名。旧 run 若手工命名为 `run.v1`、带空格或超过 128 字符，将从“可读”变为 `INVALID_ARGUMENT`。设计说“旧合法 run 保持兼容”，但“合法”未定义；建议在 README 明确“只有符合 ID 字符集的目录可读”，或对 exact 目录放宽（仍做 inside 校验）。P3。

**P3-11 重复完整哈希/保存模式双次 load_run（作者已披露延后；静态+代码位置）**

- `cli.py:649-650` 保存模式 `run_gate` 内已 `load_run`，再 `load_run` 取 run_dir；每次 load 对 5 个依赖各验两遍 → 最多 4 次全量哈希。`--no-save` 已跳过第二次。性能项，不影响正确性。

**P3-12 run 来源/项目归属未校验（服务层身份约束；已实测）**

- `load_run` 只校验 run_id 与目录名、路径在 audits 内；不比较 `summary.project_root` 与请求项目。把 `probe6/C` 的 legacy run 复制进新建项目 `probe10/audits/legacy`，`gate --project probe10 --run legacy` → **exit 0、passed=true**（PID 46104，`logs/misc_verify.json`），说明 B 项目会把 A 项目的 run 当合法历史读取（marker/摘要都自洽）。MCP 的 `runs_list`/`findings_get` 若按目录发现历史，必须自行绑定 state/项目，或至少披露“run 内容可来自复制”。可信项目边界内风险低，P3。

**P3-13 coverage 读取的 TOCTOU**（静态推断）

- `gate.py:89-99` 在 `load_run` 校验后直接读 `raw/coverage.json`；并发替换可改变覆盖率门。design 已声明不承诺原子快照、只降低误判；与 inputs 的两次枚举同理。记录，不阻断。

**P3-14 scan 产物也变成紧凑 LF JSON（不止 gate/diff）**

- `scan.py:116-123` 用 `atomic_json` 写 inputs/summary/findings，report 用 `atomic_text`（newline="\n"）；旧产物是 `indent=2` + 平台换行。设计只明说 gate/diff 格式变化；scan 产物的格式/换行变化未单独列出（值/语义不变，MCP 解析 JSON）。建议发布说明补一句。

**P3-15 全 error/timeout 时控制台仍打印“所有工具都 skipped”**

- `cli.py:857-863`：`runnable = [r for r in out.results if r.status == "ok"]` 为空即打印“所有工具都 skipped”；真实 pytest error 的 scan 也打印该句（`logs/repro_pids.json` scan_console_leak 的 stderr）。措辞误导，P3。

**P3-16 `verify_publication` 直接调用时不重锚项目根**（静态推断）

- `evidence.py:120-162` 只校验 `run_dir` 与文件相对关系；若调用方传一个指向项目外的 junction 作为 `run_dir`，`inside(run_dir/name, run_dir)` 两边一起解析，仍会通过。`load_run` 已在 `resolve_run_dir` 做归属，所以核心路径安全；MCP 不应把未验证路径直接传给 `verify_publication`。API 契约需写明，P3。

**P3-17 `Config._apply` 的 bool 强转（preexisting，不在本批 diff）**

- `config.py:139-143` `no_deepsec`/`respect_gitignore` 用 `bool(...)`；TOML 里写成字符串 `"false"` 会变 True，静默改变安全/范围。属 HEAD 既有；本批未改。记录，避免把它当本轮回归。

---

## 2. 旧发现逐项核对

### 2.1 DeepSeek r01

| 旧项 | 状态 | 依据 |
|---|---|---|
| P1-1 改 schema 关闭证据链 | **已修复** | 我的组合矩阵：schema=2 + marker + inputs → LOADED；schema=3/"2"/2.0/True/None、marker/inputs 任一缺失或多余 → INVALID_ARTIFACT/RUN_NOT_READY；删除 schema 且重发布一致 marker → INVALID_ARTIFACT（missing schema）；`schema=None, marker=False, inputs=False` → 正常 legacy 正控；第二遍校验期间改 findings → INVALID_ARTIFACT。`runs.py:116-128` |
| P2-1 Windows 大小写 | **已修复** | `REVIEW-RUN`、`REVIEW-` 在 Windows 解析到 `review-run`；`DUP-A` → `dup-a`；写入侧同 ID 大小写碰撞仍 RUN_COLLISION 且不改旧字节；prefix 用 `os.path.normcase`（`runs.py:74-80`） |
| P2-2 读取越界 | **部分修复** | audits 根 junction、run 目录 junction、`../`/盘符/反斜杠/设备名/空/超长引用均拒绝（OUTSIDE_PROJECT/INVALID_ARGUMENT）；**但 `audits/baselines` junction 可读项目外基线**（本报告 P2-1），legacy coverage 读取也未做归属；写侧 baseline junction 可写到项目外（本报告 P3-3） |
| P2-3 脱敏缺口 | **部分修复** | inputs.json、scan JSON stdout、inputs full/summary 均不再含已知 token，产物/错误 envelope 干净；但 md 控制台 reason、legacy gate stdout 仍未脱敏（本报告 P2-3） |
| P2-4 effective_adapters | **已修复（按新契约）** | `selected_adapters`、`effective_adapters`（选定别名）、`attempted`（非 skipped）、`completed`（ok）、`skipped` 均存在；真实 pytest skipped/timeout/error 三态实测正确；但 core gate 仍不消费 skipped（本报告 P2-4） |
| P3-1 inputs 期限未记录 | **已修复** | summary `inputs_timeout_seconds=120.0`；`--inputs-timeout-seconds 601/0` 在建目录前 exit3 INVALID_ARGUMENT；0.000001 真实超时 exit2 INPUTS_TIMEOUT、无 marker |
| P3-2 FileNotFoundError 捕获顺序 | **已修复** | `cli.py:797-800` FileNotFoundError 在 OSError 前；项目不存在仍 exit1，目录竞态不再被错标 IO_ERROR |
| P3-3 第二次 verify 异常类型 | **已修复** | 两次均包成 RunNotFoundError；确定性改 findings 后第二遍 INVALID_ARTIFACT |
| P3-4 coverage 最终字节被重写 | **部分（scan 侧修，生产者侧未修）** | r01 指的 scan `read_text/atomic_text` 已删，改为 `sync_file`；但真实 pytest adapter 仍 `read_text`+`write_raw`，LF/非法 UTF-8/凭据路径都会改字节（本报告 P3-1）；真实单行 coverage.py 输出恰好不变 |
| P3-5 无目录 fsync | **不适用（已披露未修）** | `atomic_text` 只 fsync 文件；设计明确不承诺目录 fsync/断电事务；失效方向是标记有数据不符（fail-closed） |
| P3-6 标记无自摘要 | **不适用（已披露）** | marker 是结构化元数据，不是签名；语义字段都校验 |
| P3-7 半写 run 与不存在不可区分 | **已修复（exact）** | exact 目录无 summary → RUN_NOT_READY；但 prefix 只匹配有 summary 的目录，空 half-run 仍不会被前缀发现；空目录仍保留 |
| P3-8 prefix 大小写 | **已修复** | normcase 前缀匹配；Windows 实测 |
| P3-9 32k 期限余量 | **未改（能力保留）** | 32k 120s 证据成立；scan 默认仍 60s/阶段；作者未承诺大仓必过，只给可调；非缺陷 |
| P3-10 重复哈希 | **未修（延后）** | 保存模式双 load_run + 每次双 verify（本报告 P3-11） |
| P3-11 gitignore 子集 | **未修（保留）** | 单段目录名/通配/exact 文件支持；`sub/dir/`、`sub/*.py` 不支持（本报告 P3-5）；本仓 ignored 夹具 6 文件仍被监视 |
| P3-12 文档未更新 | **已修复** | README/agent-adapters README 已写入 `--run-id`、`--inputs-timeout-seconds`、`inputs --summary`、`--no-save`、RUN_COLLISION、LF 紧凑 JSON、inputs_timeout 记录 |

### 2.2 GLM r01

| 旧项 | 状态 | 依据 |
|---|---|---|
| P2-1 非 UTF-8 产物字节 → INVALID_ARGUMENT/traceback | **已修复（产物层）** | marker/summary/findings 写入 `\xff\xfe{}`：gate/diff/triage exit3 INVALID_ARTIFACT、JSON error、无 traceback；baseline/fix/suppress exit3 文本错误、无 traceback；load_run 两遍均 INVALID。**但非 UTF-8 文件名是新缺口**（本报告 P2-2） |
| P3-1 捕获顺序 | **已修复** | 见 DS P3-2 |
| P3-2 Bearer 行文误报 | **部分修复** | 小写短词不再误报；大写 `Bearer authentication` 仍被替换（本报告 P3-2） |
| P3-3 Authorization Basic | **已修复** | `Authorization: Basic`、`Proxy-Authorization: Bearer`、`Authorization: Bearer` 均替换；`Authorization: Token` 仍不覆盖（已知形态限制，设计只承诺 Basic/Bearer） |
| P3-4 项目外 symlink .py 使 scan 失败 | **保持 fail-closed + 已文档化** | 设计写明项目外源链接 OUTSIDE_PROJECT；我用目录 junction 实测监视阶段 OUTSIDE_PROJECT；文件 symlink 因本机无 SeCreateSymbolicLinkPrivilege 未跑（如实标注） |
| P3-5 gate 保存路径重复 load_run | **未修** | `cli.py:649-650` 仍在保存模式二次 load；性能 |
| P3-6 gate/diff 落盘格式变紧凑 LF | **已改 + 已披露** | 实测 gate.json/diff.json 无 CRLF、键排序、紧凑；`--no-save` 与保存模式 payload 完全相等；设计/README 提到 |
| P3-7 证据精度（32k/格式计数/计时） | **部分更新** | 本轮 32k 为 11,968,784/773（r01 是 9,312,754/743），我复算一致；format 57 文件、mypy 31；首轮 facts 失败保留；计时口径作者已改为“含解析、非纯监视”；未复测墙时 |
| P3-8 观察项 | **部分** | inputs.json 路径已脱敏且可复算；resolve_run_dir 路径引用已核心校验；设备名 run 已拒；但 baseline 名设备/长度未管（本报告 P3-3）；scan 仍就地改 `cfg.enabled_adapters/python`（不变）；目录 fsync 仍未做（已披露） |

---

## 3. 材料与来源核验（全部自行复算）

### 3.1 ZIP 与成员

| 项目 | 声明 | 复算 | 判定 |
|---|---|---|---|
| ZIP 文件字节数 | 3,791,715 | 3,791,715 | 一致（这是压缩包大小，不是解压总字节） |
| SHA256（全长） | `32b1be9a…15c13` | `32b1be9ac3102c519f9725175963edec2d675dd57ac6a01a38271053dc415c13` | 一致 |
| 成员数 | 345 | 345（无目录项、无加密成员） | 一致 |
| 压缩数据字节 | — | 3,722,059（+ 头/中央目录 = 3,791,715） | 记录 |
| 解压总字节 | — | **45,649,362**（manifest 声明 344 项合计 45,584,989；差 64,373 = manifest 自身） | 记录 |
| CRC | — | `zipfile.testzip() is None`；逐成员全量读取无异常 | 通过 |
| 成员唯一性 | — | 345 个名字全唯一；无重名 | 通过 |
| 路径安全 | — | 绝对路径 0、盘符 0、`..` 0、`.` 段 0、反斜杠 0、冒号/ADS 0、尾点/尾空格 0、Windows 保留名 0、空段 0 | 通过（解压前拒绝） |
| Windows 覆盖冲突 | — | 按大小写折叠 + 去尾点/空格后 0 组冲突 | 通过 |
| 解压落盘 | — | 345/345 文件，逐成员 realpath 均在目标根内 | 通过 |

### 3.2 manifest

- `manifest.json` 64,373 字节；raw SHA256 `2b7f594625f10bc8d578c592d0b71d193813f049a66646c696dd60b10346db47`；规范化（UTF-8、sort_keys、紧凑分隔符）SHA256 `deaf7ecb1a09d849f5492cdaa528e2406c6fe417ad7897628d861983083489e6`。
- 声明 344 个文件；ZIP 非 manifest 成员 344 个；**双向差集均为空**；manifest 不自声明。
- 逐项重算 SHA256 与字节数：**344/344 全等，0 失配**；声明合计 45,584,989 字节。
- `candidates` 恰 12 项，全部在声明集与 ZIP 中；`review_input_sha256` 的两份 r01 审核文件哈希与包内实际字节全等（DeepSeek `af99960c…`、GLM `5cbcbb76…`）。
- `kind=core-review-fixes-r02-only`、`head=252ec3c…`、`gate_A_exit_code=1`、`mcp_service_implemented=false`、`committed/published=false`，与包内证据口径一致。

### 3.3 候选树重建（HEAD + 12 候选，未用脏工作区冒充）

1. `git -C 主仓 archive --format=zip 252ec3c…` → 67 文件，exit 0。
2. 解到 `candidate-tree/`；再覆盖 ZIP 原字节的 12 个候选；最终 70 文件（67 + 3 新增）。
3. 12/12 候选 SHA256 与 manifest 相等。
4. 非候选 58 个文件：与 HEAD 内容逐行规范化后**全等**；差异集恰为 manifest 的 12 项（9 改 + 3 新）。
5. `tracked-candidate-diff.patch` 只覆盖 9 个已跟踪文件；对 `head-tree/` 执行 `git apply --check` → exit 0。
6. `evidence.py`、`tests/mcp/test_core_evidence.py`、`tests/mcp/test_core_review_regressions.py` 在 HEAD 不存在，确为新增。
7. `pyproject.toml`、`.cq/suppressions.json`、`gate.py`、`diff.py`、`baseline.py`、`report.py`、`schema.py`、`suppress.py` 与 HEAD 规范化内容全等；`.cq/suppressions.json` 候选与主仓工作区**逐字节相同**（673 字节，18 个 CRLF）。

**字节 vs 规范内容的区别（按启动词要求显式区分，不静默归一化）：**

- ZIP 的 12 个候选文件与主仓当前工作区**逐字节相同**（12/12；README/agent-adapters README/cli.py/config.py/scan.py 含 CRLF，其余 LF），所以候选没有漂移。
- `git archive` 在本机受 `core.autocrlf=true` 影响，把 HEAD 文件写成 CRLF；主仓当前工作区多数 HEAD 文件是 LF（例如 `pyproject.toml`：候选树 1728 字节/48 CRLF，工作区 1680 字节/0 CRLF；`gate.py`：9928/272 vs 9656/0）。**内容相同、原始字节不同**。因此：
  - “候选树与 HEAD 内容一致”成立；
  - “候选树与工作区逐字节一致”对 12 个候选成立，对 HEAD 派生文件不成立，不能混称。
- `source-baseline.json` 仅为旧基线，未当作本轮候选摘要；没有用主仓最新工作区补任何候选。

### 3.4 32k 清单证据（只复算，不重建物理 32k 文件）

- 包内 `inventory-full-…stdout` 实测 **11,968,784 字节**、32,000 条；`inventory-summary-…stdout` **773 字节**。两条记录 exit_code 均 0，argv 为 `inputs --project <Temp 夹具> --timeout-seconds 120 [--summary]`，cwd 为主仓，seconds 记录 73.33870620000016 / 66.91461229999913。
- 独立复算（不再调用作者的 assert）：
  - 排除 `monitor_digest/files_count/checked_at` 后规范 JSON 的 SHA256 == 文件内 `monitor_digest` == summary 的 `monitor_digest`：**True**；用 `json.dumps(sort_keys, separators)` 的独立实现同样相等。
  - summary 与 full 去掉 `files` 后逐字段相等（含 config_digests、rules_version=2、redaction_rules_version=3、monitor_scope、respect_gitignore）。
  - 32,000 条 `path_sha256` 全部等于 `sha256(path.encode("utf-8"))`；32,000 个 path 与 path_sha 均唯一；无 `***REDACTED***` 路径。
  - 32,000 条文件 `sha256` **全部等于 `sha256(b"value = 1\n")`（`585c9366…`）**；这与作者 `package.py:40` 的断言一致，说明夹具内容为统一常量。也就是说：**文件内容摘要只验证了“与声明的夹具内容一致”，没有、也无法在无物理夹具时重算真实磁盘内容**；本报告不把它称为“32k 物理重跑”。
  - 13 个配置项（含 `.cq/suppressions.json`）逐项在 `config_digests` 中；`monitor_scope` 声明为监视集合。
- **未重建物理 32k 夹具**：时间/磁盘风险不划算；只做上述复算。作者墙时含调用方读取/解析且同机有并行活动，不能当纯监视时长或吞吐对照，我未复测。
- manifest 的 `current_monitor_matches_final_run=true`：我在主仓只读重算 `monitor_inputs`，digest = `55af075f4bc73cb09d900d21dd2e399a254676484b1a332f86cc30e6b3320f99`，与最终 run 04 的 `inputs.after.monitor_digest` **相等**。但这不是候选树的 digest：候选树只有 57 个 `.py`，主仓工作区有 63 个，多出的 6 个是 `.gitignore` 里被忽略的 `tests/fixtures/demo-flask-api/*.py`（见本报告 P3-5）；候选树 `pyproject.toml/.gitignore` 的 **CRLF 原始字节**也与工作区 LF 不同。因此“当前工作区监视摘要匹配”成立，“候选树监视摘要匹配”不成立，原因是工作区含被忽略夹具与行尾差异，不是候选内容漂移。

### 3.5 最终 run `cq-mcp-core-20261025-04`

- marker 结构：`schema_version=2`、`run_id=cq-mcp-core-20261025-04`、`cq_version=0.5.2`、`files` 恰 5 项；我逐文件 `hashlib.sha256(bytes)` 重算，**5/5 与 marker 相等**（coverage 存在，非 absent）。
- summary：schema 2、`scan_consistency=consistent`、`inputs_timeout_seconds=120.0`、`redaction_rules_version=3`；`tools` 为 7 个 ok + import-linter skipped，selected 8 项、attempted/completed 各 7、skipped 1。
- coverage：`2810/3357 = 83.70568960381293%`，与 summary/author 一致；`raw/coverage.json` 179,647 字节、**LF 计数 0、CRLF 计数 0（单行 JSON）**，未被文本换行重写（这一实例恰好能保持原字节，原因见本报告 P3-1）。
- `load_run` 用候选代码可读该 run；`gate`/`diff` 给出领域 exit1（见 3.6，不是产物损坏）。

### 3.6 A 门归因（独立核对，不采信作者陈述）

- 基线 `audits/baselines/cq-mcp-before-20261025.json`：`source_run_id=20261025-130607-full`；blocker 为 `deepsec:hardcoded_secret_database_url @ src/ai_code_quality/redact.py:37`，id `a66a2892c00ab4ffcad6a7f45b58d3734384b6b6`，message `Database URL includes a password.`，status=suppressed；另有 runner.py:51 high，id `8e2e92a3…` 且未漂移。
- 当前 run：同一 finding 变为 `redact.py:46`，id `75b368448e416b71c8c42f72af89570a04d0a3b8`，status=new。用 `schema.make_id` 复算：line 37 → `a66a2892…`，line 46 → `75b36844…`，**完全对应**。
- 候选 `redact.py:46` 内容为 `    # 连接串里的密码：postgres://user:pass@host`，是注释里的占位示例，不是真实凭据；误报判断由内容独立证实。
- `.cq/suppressions.json` 两条登记只有 `id/action/reason/created_at/source_run`，**没有 sig/source/rule/file/message**；行号漂移后 id 失配，`suppress._entry_sig` 无法对齐，`--reapply` 也无效。这是登记决策，不是本批代码可修；不应改登记换绿门。
- MI：`radon.metrics.mi_visit` 精确复算候选 `cli.py = 7.267599723418189`（C），HEAD `11.673489845205554`（B）；author 值一致，真实低危，不参与 gate 检查。
- gate A：exit **1**；checks 中 `blockers` 失败（1/0），`highs/complexity/coverage` 通过，`new_blocker_high` 失败；ratings security D、其余 A；`tools_ok` 文案问题见 P2-4。
- diff：exit **1**；new 2、fixed 0、existing 0、suppressed 1；new_details 含上述 blocker 与 radon MI low。
- 结论：A 门红是“同一历史误报因行号漂移重新暴露 + 新增低危 MI”的合法算法输出，不是本批新引入的安全/可靠性缺陷；它不构成进入下一阶段的技术阻断，但也不得被表述为门绿。作者的归因成立。

### 3.7 作者声明核对（摘要）

| 声明 | 复核 | 判定 |
|---|---|---|
| 260/260（原 214 + 46），tests/mcp 79 是子集 | 我独立跑出 **260 collected / 260 passed**；tests/mcp **79**；0 fail/error/skip；exit 0；17.1 s | 成立 |
| ruff / format / mypy | `ruff check src tests` exit0；`ruff format --check src tests` “57 files already formatted” exit0；`mypy src` 31 源文件 0 问题 | 成立 |
| 解释器未装 mcp | `find_spec("mcp")` 为 None | 成立 |
| 最终自扫七工具 ok、import-linter skipped、consistent | 逐项核对 summary 与 marker；5/5 摘要 | 成立 |
| 覆盖率 2810/3357 | 精确复算一致 | 成立 |
| 32k 11,968,784 / 773 / 两次 exit0 / 120s | 字节与 exit 记录一致；摘要复算一致；未重建物理夹具、未复测墙时 | 记录成立（复算） |
| 输入清单前/后摘要可复算 | 最终 run 的 before/after 均用规范对象复算相等 | 成立 |
| `--no-save` 零写入 | 新建 run 上 gate/diff `--no-save` 不产生 gate.json/diff.json；已保存文件字节不变；marker 不变 | 成立 |
| 正式 `.cq`、gate.py、diff.py、pyproject、阈值未变 | `.cq` 与 HEAD/工作区逐字节同；gate.py/diff.py 内容与 HEAD 同；gate/diff 对同一 legacy run 的 JSON 输出与 HEAD **完全相等**；pyproject 内容同 | 成立 |
| 首轮 79 项 5 失败、初轮 lint 失败、facts 脚本 LF/CRLF 误比失败均保留 | `regressions.xml` tests=79 failures=5（含 Bad file descriptor 的 fsync 夹具）；`check-…json` exit1（输出含 SIM102/F401 等）、`check-r02…` exit0；`facts-final-…stderr` 为 `AssertionError`（verify_results.py:66）且 exit1，随后 `facts-final-r02` exit0 | 成立 |
| 03 是中间版本、不是最终快照 | 包内 03/04 并存；我未把 03 当候选源码 | 成立 |

---

## 4. “修订是否引入新问题”与作者结论的分歧

**r02 新引入/新暴露（相对 r01/HEAD）：**

1. `monitor_inputs` 对代理字符文件名抛 UnicodeEncodeError，`inputs` 裸 traceback、`scan` 误标 exit1 + 空半写目录（P2-2，新增代码）。
2. scan 先建 run/raw 再监视，输入超时留下空目录（P3-9，顺序变化）。
3. 前缀解析对 audits 内任何越界链接整体失败（P3-6，新增 `inside` 生成器）。
4. 旧 run 名含点/空格/超长被新 `validate_id` 拒绝（P3-10，兼容收紧）。
5. `sync_file` 用 r+b，coverage 只读属性会让 scan 失败（作者首轮已从只读句柄改为 r+b；失败方向 fail-closed，属新失败面）。
6. scan 产物（不止 gate/diff）改为紧凑 LF JSON（P3-14，格式变化未逐项披露）。
7. `publish_run` 对 coverage 目录按 absent 处理（P3-8，防御性边界）。

**不是新引入，但 r02 仍未覆盖/声明过宽：**

- baseline 读取链（P2-1）与 baseline CLI 边界（P3-3）：HEAD 既有代码，r02 宣称“读取防线”但未含 baseline。
- md 控制台/legacy gate 脱敏（P2-3）：HEAD 既有，r02 只修了 scan JSON/inputs。
- core gate skipped 语义（P2-4）：gate.py 未改，r02 只修 summary。
- coverage 生产者文本重写（P3-1）：adapter 未改，r02 修了 scan 侧并加了绕过生产者的测试。
- `.gitignore` 相对目录/带斜杠 glob（P3-5）：`_Gitignore` 未改，r02 新增 monitor 使用后更可见。

**与作者结论的分歧：**

- 作者 `core-review-fixes.md`：“作者复验未发现剩余的本批进入服务层阻断项”“coverage 只 fsync 原字节，不经文本换行转换”“保留正常 bearer 英文行文”“marker/summary/findings 二进制损坏六类 CLI 不裸崩溃”。
  - 前两句在字面上不成立（P3-1、P3-2）；
  - “六类 CLI 不裸崩溃”对 marker/summary/findings 成立，但 baseline JSON 形状损坏仍裸 traceback（P2-1），属未覆盖的读取链；
  - “无剩余阻断项”不成立：P2-1/P2-2 在 MCP 的 gate/diff/inputs 消费面上，P2-3/P2-4 是必须在 MCP 契约中落实的归属与语义。
- 作者 A 门归因、失败轮保留、260/79、覆盖率、32k 摘要、最终 run 标记等声明均可复算成立；本报告不因 A 门红否定本轮修复，也不把 A 门红当成本批缺陷。

---

## 5. 实跑 / 未跑、证据与测试盲区

### 5.1 实跑（全部在独占候选树/夹具，未改候选源码或测试）

| 检查 | 命令要点（cwd） | 结果 |
|---|---|---|
| 完整回归 | `python -m pytest tests -q`（candidate-tree） | **260 passed**，exit 0，17.1 s（PID 36748 宿主）；tests/mcp **79** |
| ruff / format / mypy | `python -m ruff check src tests`；`ruff format --check src tests`；`mypy src` | 全部 exit 0；“57 files already formatted”；31 源文件 |
| 候选树自建核对 | `head-tree.zip` + 12 覆盖 | 70 文件；12/12 manifest；非候选 58 内容同 HEAD；patch apply check exit0 |
| 反例组 1 | `probe1.py`（schema 组合、五类依赖 × 6 CLI、baseline 形状） | 109 条记录；组合矩阵 24 组；依赖 12 情形 × 6 消费者；baseline 形状 4 条 traceback |
| 反例组 2 | `probe2.py`（audits/run/baselines junction、引用形状、baseline 名） | 33 条；junction 越界拒绝/基线读穿；33 引用形状 |
| 反例组 3 | `probe3.py`（inputs v2、脱敏、泄露、期限、代理字符） | 21 条；摘要可复算；已知 token 产物干净；控制台泄露；代理字符 UnicodeEncodeError |
| 反例组 4 | `probe4.py`（coverage 真实方法、adapter 语义、退出码、保存格式、HEAD 等价、解释器来源） | 24 条；coverage 字节表；gate/diff JSON 与 HEAD 完全相等；python_source 四态 |
| 反例组 5 | `probe5.py`（真 timeout/error、inputs 超时、baseline 遮蔽、脱敏行文、默认同秒碰撞） | 24 条；timeout/error 标记发布但 gate exit2；inputs 超时空目录；大写 bearer 误报 |
| 反例组 6 | `probe6.py`（前缀 junction、baseline 形状/写侧、legacy 泄露、summary 目录、audits 文件） | 8 条；P2/P3 证据 |
| 关键复现 PID | `repro_pids.py` → `logs/repro_pids.json`；`logs/surrogate_fresh.json` | baseline 41992/41452、junction 21868、代理字符 inputs 46076/45336、控制台 44332、A 门 46936/28720、timeout gate 41968、real scan 38824、copied run 46104 |
| 全 skipped gate | `logs/skip_gate.json` | scan 43100 / gate 37664；gate exit0/passed |
| 32k 复算 | `verify_evidence.py` | digest 三处相等、32k 路径身份、内容常量 |
| 最终 run 校验 | 逐文件 SHA + marker + coverage 算术 | 5/5、2810/3357 |
| A 门 | `gateA`/`diffA`（候选 CLI，复制 run+baseline 到夹具） | gate exit1、diff exit1；new2/fixed0/existing0/suppressed1 |
| 真实 scan 冒烟 | `scan --adapters ruff-check --run-id r1/r2` | exit0（PID 38824，0.803 s）、5 依赖 + marker、gate/diff 可读 |

解释器与 cwd、argv、exit、耗时见 `logs/probe*.json`、`logs/repro_pids.json`、`logs/skip_gate.json`；标准输出/错误见 `logs/probe*.txt`。所有夹具在 `fixtures/`；未向主仓写任何文件，未执行作者 verify 脚本，未安装依赖，未启动服务，未联网/调用 provider，未读凭据/.env。

**证据完整性披露**：批量探针（probe1-6）逐条记录输入、结果、exit/部分头部输出，但脚本最初没有逐条保存子进程 PID/完整 argv；关键 P2 复现已用 Popen 补采 PID/argv/cwd/exit/秒数（`repro_pids.json`、`surrogate_fresh.json`、`misc_verify.json`、`skip_gate.json`）。未补采者不冒充“逐条 PID 证据”；命令表给出可重跑的命令要点。probe*.txt 是宿主控制台汇总，不是每条子进程的完整 stdout/stderr 原件。

### 5.2 未跑（不得据本报告声称）

- 物理 32k 夹具重建/重跑与墙时复测（只复算包内 11,968,784 字节对象；时间来自作者记录）；
- POSIX/Linux 行为、POSIX symlink 文件（本机无 SeCreateSymbolicLinkPrivilege，WinError 1314）、大小写敏感文件系统；
- Python 3.11 真机（3.13.14 only；mypy 按 3.11 配置）；
- 真实强杀/断电/目录 fsync 持久性（只做真实限期超时与只读 coverage 的 fsync 失败；后者见下）；
- 真实 MCP SDK/两个宿主/九工具/账本/锁/分页（本批未实现，mcp 包不存在）；
- ACL/多用户/网络文件系统；恶意仓库沙箱（明确边界外）；
- 并发第二遍校验的真实竞态（用确定性文件改写 hook 触发，不冒充并发压力测试）。

补充：真实 fsync 失败路径用自定义 adapter 在 `raw/coverage.json` 写入后设只读属性，`scan` 抛 `PermissionError`、marker 不存在、残留 inputs.json/coverage.json（`fixtures/probe7`）。adapter 是测试夹具（为制造 coverage），被测 candidate 代码未改；该路径证明失败方向 fail-closed，但不是真实断电。

### 5.3 新测试（46 项）的盲区（我实际补到的）

1. coverage 原字节测试用假 adapter `write_bytes`，绕过真实 `pytest_cov._coverage_section`（P3-1）。
2. Bearer 行文只测 `the bearer of bad news`，未测大写/长词（P3-2）。
3. schema 删除用例在改 summary 后未同步重发布 marker，失败可由摘要不符触发，未隔离“缺 schema 字段”分支；我用重发布一致 marker 单独验证，代码本身能拒绝（结论仍为已修复）。
4. 无 baseline JSON 形状/类型/junction/写侧测试（P2-1、P3-3）。
5. 无代理字符/非 UTF-8 文件名测试（P2-2）。
6. 无 md 控制台 reason、legacy gate stdout 泄露测试（P2-3）。
7. 无全 skipped/部分 skipped 的 gate 语义测试（P2-4）。
8. 无真实 timeout/error adapter 的 gate 映射测试（新测试用 monkeypatch status；我补了真实 pytest timeout/error）。
9. 无 prefix 遇 audits 内越界 junction 的测试（P3-6）。
10. 无 `summary.json` 为目录、`publish_run` coverage 为目录的测试（P3-7/P3-8）。
11. 第二次校验用 monkeypatch 抛异常，未做真实文件在两次读之间变化的测试（我补了确定性改写）。
12. 无 `inputs` 真实期限超时（新测试 monkeypatch `monitor_inputs`；我补了真实 0.000001 s）。

这些盲区不否定 46 项的价值：它们覆盖了标记缺失/损坏、findings schema、六写点中断、coverage absent/出现、碰撞不改字节、显式空 adapter、非法 ID、--no-save、读写 exit4、红名输入摘要等核心性质；但“作者测试全绿”不能替代上述独立反例。

---

## 6. 残余风险与不能声称的内容

**即使列明问题修复后仍存在：**

- 有权限者整体重写 marker + 五件套可使校验通过；marker 不是签名，威胁模型不防。
- 无目录 fsync/断电事务；进程崩溃可检测（marker 后写），掉电语义不保证。
- 监视集合 ≠ 分析器实际读取全集；`.gitignore` 子集对相对目录/带斜杠 glob 不生效；项目外工具配置/动态依赖不覆盖。
- `scan_consistency=consistent` 只表示两次监视摘要相同，不是文件系统原子快照；读完后到 after 之间仍有窗口。
- coverage 在生产者侧被文本解码/重写（P3-1）；对真实单行输出通常无影响，但不能称为“分析器原字节”。
- baseline payload 不含 comparability 字段；MCP 需要源 run 或 comparable=false。
- gate/diff 的 coverage 读取在 load_run 之后，存在并发替换窗口。
- run 内容可来自其他项目复制；MCP 的项目/state 绑定必须另做。
- 恶意项目沙箱、跨用户、跨平台、真实宿主、产品锁/进程域均不在本批保证内。

**不得声称：**

- 不得声称 MCP 九工具/台账/锁/进程域/分页/verdict 已实现或可用；包内 manifest 自述 `mcp_service_implemented=false`。
- 不得声称门绿或发布通过；A 门 exit1，正式 `.cq`/阈值未改。
- 不得声称跨平台/双宿主/3.11/真实断电已验收。
- 不得声称 coverage 字节在一切情形下等于分析器原字节，或“所有输出”都已脱敏。
- 不得把 260/260、32k 摘要复算、A 门归因当作产品发布验收。

---

## 7. 进入服务层的判断

**修复列明问题后可进入 MCP 服务层。**

进入前必须完成（按优先级）：

1. **P2-1** 基线读取链：`inside()` 归属校验 + baseline JSON 形状校验 + gate/diff 结构化错误（INVALID_ARTIFACT/exit3），并加负控；或在 MCP 契约中明确承担并测试“核心不保证 baseline 读取归属/形状”。我建议核心修，成本低。
2. **P2-2** 代理字符/非 UTF-8 文件名：`monitor_inputs` 归一为 INPUTS_UNAVAILABLE，`inputs` 走 JSON error，`scan` exit2 而非 exit1；加负控。
3. **P2-3** 脱敏归属：md 控制台 `reason` 过规则；gate/diff 快照由 MCP 过规则（或核心一并做），并测试 legacy/md 两条通道。
4. **P2-4** MCP verdict：selected 但 skipped/缺失/禁用一律 runtime gap → cannot_judge，不把 `core_gate.passed` 当最终通过；测试全 skipped、部分 skipped、timeout。
5. 纠正声明/测试：P3-1 coverage（改字节复制或改声明与测试）、P3-2 Bearer 大写行文；否则不要把这两条作为对 MCP 的保证引用。

不阻断但应记录/排期：P3-3 baseline CLI、P3-4 baseline payload/comparability、P3-5 gitignore 子集、P3-6 前缀粗失败、P3-7 分类、P3-8 coverage 目录、P3-9 空半写目录、P3-10 旧名兼容、P3-11 重复哈希、P3-12 provenance、P3-13 TOCTOU、P3-14 格式披露、P3-15 文案、P3-16 verify_publication API、P3-17 Config bool。

**为什么不是“可进入”**：P2-1/P2-2 会在 MCP 的 gate/diff/inputs 路径上产生裸 traceback 或业务 exit1，P2-3/P2-4 是必须在契约里落实的脱敏与 verdict 语义；作者的“无剩余阻断项”过强。
**为什么不是“暂不可进入”**：没有 P0/P1；单字段 schema 绕过、run/audits 归属、完成标记/五类摘要、二进制产物损坏、inputs v2 身份与可复算、adapter 语义、--no-save、gate/diff 算法未改等核心性质均经独立实跑成立。剩余问题是有界、可在服务层施工前以数行到十余行修复或用契约+测试显式承担的，不是架构问题。

---

## 附录 A：关键证据指针

- 材料：`logs/inventory.txt`、`logs/manifest_verify.txt`、`logs/extract.txt`、`logs\diff_small.txt`、`manifest.json`、`zip_members.txt`
- 反例：`logs/probe1.json`、`probe2.json`、`probe3.json`、`probe4.json`、`probe5.json`、`probe6.json`、`skip_gate.json`、`repro_pids.json`、`surrogate_fresh.json`、`misc_verify.json`
- 证据复算：`logs/verify_evidence.txt`、`logs/verify_gate.txt`、`logs/gateA.full.json`、`logs/diffA.full.json`
- pytest/质量：`logs/pytest-full.txt`、`head-tree/`、`candidate-tree/`
- 32k：`zip-extract/audits/cq-mcp-review-fixes-20261025-01/inventory-full-1792908854573905400.stdout`、`inventory-summary-1792908927913870000.stdout`
- 最终 run：`zip-extract/audits/cq-mcp-core-20261025-04/`
- A 门基线：`zip-extract/audits/baselines/cq-mcp-before-20261025.json`

## 附录 B：关键代码位置索引

- 证据/标记：`evidence.py:34-47/78-98/101-162`
- run 读取：`runs.py:59-86/89-113/116-128/131-144`
- 输入监视：`targets.py:121-201/204-205/208-265`
- 扫描发布：`scan.py:48-134/137-145/217-291`
- CLI：`cli.py:571-674/758-863/830-846`
- 基线：`baseline.py:23-68`
- gate/diff：`gate.py:89-99/121-131`、`diff.py:44-116`
- 脱敏：`redact.py:14-53`
- 控制台：`report.py:183-205`
- coverage 生产：`adapters/pytest_cov.py:233-268`、`adapters/base.py:83-90`
- adapter 注册：`adapters/__init__.py:29-37`

---

本文件只评价本批核心实现与直接调用链，不评价另一位审核者本轮输出，不修改实现，不构成发布验收。
