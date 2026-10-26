# cq MCP 核心首批实现 独立审核（DeepSeek）

- 审核对象：`cq-MCP-核心首批实施与证据-20261025-r01.zip`（208 成员）
- 固定旧基线：`252ec3cf5bd3ca3024ab8dc0ee7111f6573ccad7`
- 审核日期：2026-10-25（Asia/Shanghai）
- 审核范围：9 个候选文件（7 改 + 2 新增）及其直接调用链；MCP 服务层、SQLite 台账、九工具、verdict、分页、真实宿主不在本批
- 结论（详见 §8）：**修复列明问题后可进入 MCP 服务层**。P1 一条必须先在核心修复；P2 四条需在 MCP 层施工前修复或明确移交并在契约中承担。

本文件是**实现审查**，不是发布验收，不构成对 MCP 方案或整体发布的通过。

---

## 1. 材料核验

全部由本轮自行复算，不接受摘要前缀作为一致证明。

| 项目 | 声明 | 复算结果 | 判定 |
|---|---|---|---|
| ZIP 字节数 | 1,553,377 | 1,553,377 | 一致 |
| ZIP SHA256 | `1a48db80…5fadf1` | `1a48db807b4dcc933467873fc86faa70c17ac978a87114721bae5463075fadf1` | 一致（64 位全等） |
| 成员数 | 208 | 208（无目录项、无加密成员） | 一致 |
| 成员独占性 | — | 重名成员 0 | 通过 |
| 逐成员 CRC | — | 208/208 与中央目录 CRC32 相符；解压后字节数 208/208 相符；读取异常 0 | 通过 |
| manifest 覆盖 | 其余 207 项 | 207 条 = ZIP 非 manifest 成员全集（双向差集均为空） | 通过 |
| manifest 摘要 | — | 207/207 SHA256 与字节数全等（0 失配） | 通过 |
| manifest 自身 | — | 37,743 字节，`sha256=6bf0e436179e31584b1026d3e19f47725dae1d382df89a377d9291818f28de37`；`kind=core-implementation-review-only`、`head=252ec3c…`、`gate_A_exit_code=1`、`committed/published=false`、`mcp_service_implemented=false` | 与实施记录口径一致 |
| 成员路径安全 | — | 绝对路径 0、盘符 0、`..` 0、反斜杠 0、冒号/ADS 0、首尾空白 0、尾点 0 | 通过 |
| 解压后总字节 | — | 28,486,555 | 记录 |

**候选树重建**（独占目录，未覆盖主仓、未使用主仓工作区作为候选）：

1. `git -C <主仓> archive 252ec3c… | tar -x -C base252ec3` → 67 文件，exit 0；
2. `base252ec3` 复制为 `candidate`，覆盖包内 9 个候选文件；
3. 逐文件核对：9/9 与 manifest 摘要相等；
4. 反向核对：候选树中**非候选文件**与固定 HEAD 树逐字节比较，差异 **0**（说明除这 9 个文件外没有夹带改动）；
5. `evidence.py` 与 `tests/mcp/test_core_evidence.py` 在 HEAD 中不存在（确为新增）；其余 7 个在 HEAD 中存在；
6. `core-tracked-diff.patch` 只覆盖 7 个已跟踪文件，对 `base252ec3` 执行 `git apply --check` → exit 0，说明补丁与包内候选内容自洽（新增 2 文件不在 tracked diff 中，符合命名）。

**材料一致性交叉核对（未误报）**：

- 包内 `pyproject.toml` 与固定 HEAD 的**内容完全相同**，仅行尾不同（HEAD 树 CRLF 48 个，包内 LF 0 个；`git diff --no-index` 无文本差异）；包内摘要 `630d2e46…` 与 `source-baseline.json` 记录的旧摘要**相同** → 本批未改 pyproject，符合"pyproject 来自固定 HEAD"。
- `source-baseline.json` 中 `cli.py=628f2ed0…`、`scan.py=deb90ae4…`、`redact.py` 等与固定 HEAD blob 摘要一致；9 个候选中 7 个与 source-baseline 不同属**已授权变更**，未据此误报。
- 主仓当前未提交工作区的这 9 个文件，逐字节等于包内候选（9/9 manifest 摘要相等）→ 包确实代表被审对象，不是另一份快照。
- 包内 `baseline/` 8 个文件为旧材料（旧 `suppressions.json` 与 HEAD `.cq/suppressions.json` 逐字节相同），未当作候选源码使用。

**补读范围（说明）**：固定 HEAD 树中的 `src/ai_code_quality/{baseline,gate,report,schema,suppress,doctor,runner}.py`、`adapters/*.py`、`targets/scan/cli` 全量、`tests/` 目录、`.cq/suppressions.json`；主仓工作区 9 个候选文件（仅哈希比对）。**未**读取 `reviews/` 下任何既有审核文件，未读取任何其他模型的意见，未读取正式 `.cq` 之外的仓库 audits 内容（证据只从 ZIP 读）。

---

## 2. 实跑 / 未跑清单

**解释器**：`C:\Users\24701\AppData\Local\Programs\Python\Python313\python.exe`（Python 3.13.14，MSC v.1944 64bit）；pytest 9.1.1；radon 6.0.1；ruff/mypy/vulture/pytest-cov/import-linter 均可用。
**工作根**：`C:\Users\24701\Documents\deepseek-harness\default-workspace\cq-mcp-audit-deepseek-20261025-r01\`（独占新建；主仓与正式 `.cq` 未改动、未 commit）。
**证据目录**：同上 `evidence\`（`probe*-results.json`、pytest/ruff/mypy 日志）。

已跑（全部在本轮独占副本上，argv/cwd/exit 见各证据 JSON）：

| 检查 | 命令（cwd=候选树） | 结果 |
|---|---|---|
| 33 项证据用例 | `python run_pytest.py tests/mcp -q --basetemp=<workspace>` | **33 passed / 33**，exit 0 |
| 完整回归 | `python run_pytest.py tests -q` | **214 passed / 214**（3 行 72+72+70），0 fail/0 error/0 skip，exit 0；与作者 junit `tests=214 failures=0 errors=0 skipped=0` 一致 |
| ruff | `python -m ruff check .` | All checks passed，exit 0 |
| 格式 | `python -m ruff format --check .` / `... src tests` | 60 / 56 files already formatted，exit 0（作者记 56，与其范围一致） |
| 类型 | `python -m mypy src` | Success: no issues found in 31 source files，exit 0 |
| 56 项独立探针 | `python probe.py` … `probe5.py` | PASS 39 / 设计性不符合 8 / INFO 9（明细见 §3、§5） |
| 自扫证据反验 | 用候选 `verify_publication` 校验包内 `audits/cq-mcp-core-20261025-02`、`-01` | 均通过；旧 run `20261025-130607-full` 正确报 `RUN_NOT_READY` |
| 32k 清单证据复算 | 解析包内 `inventory-full-*.stdout` | 9,312,754 字节、32,000 条、summary 743 字节；**复算 `object_digest` 与文件内、summary 内三者全等**（两组独立样本均通过） |
| 自建清单实测 | 3,000 文件，`inputs` full + `--summary`，120s | full 372,814 B / 6.2 s，summary 803 B / 4.0 s，两者 `monitor_digest` 相等，exit 0/0 |

**环境说明（必须披露，非候选代码问题）**：本机沙箱下 `os.mkdir(path, 0o700)` 会产生当前账户无法枚举的目录（`PermissionError WinError 5`），而 0o755/0o777 正常；pytest 的 `tmp_path` basetemp 固定用 0o700 创建，导致首次跑测在所有使用 `tmp_path` 的夹具 setup 阶段报 `Access denied`。为取得有效结果，我用 `run_pytest.py` 包装器只把 `os.mkdir` 的 mode 强转为 0o777 后调用 `pytest.main`——**被测代码与测试文件均未修改**。该包装器与原始失败日志（`pytest-full.txt`、`pytest-mcp-01.txt`）一并保留在证据目录，未把沙箱拒绝当成代码失败，也未把 patch 后的通过当成"未经改动的原生通过"。另：`m700/`、`p700/`、`pt3/`、`pt4/` 四个空目录因该 ACL 现象无法删除，留在本轮独占目录内，未触碰主仓。

**未跑（不得据本文件声称）**：

- 真实 32,000 文件夹具的**重新生成+重跑**（仅复算了作者原始输出并自建 3,000 文件对照）；
- 进程被真实强杀（`TerminateProcess`）时的半写现场（只跑了期限超时这一条真实中断路径 + 作者的 monkeypatch 六点负控）；
- Linux/POSIX 的 `fsync`/rename 持久性、大小写敏感行为、mtime 粒度（本文相关结论均为**静态推断**，已标注）；
- MCP/SDK/两个真实宿主/VS Code 源码结论（本批范围外，未复核其证据强度）；
- 恶意仓库沙箱、跨用户、断电事务（明确不在边界内）。

---

## 3. 发现（按 P0/P1/P2/P3 排序）

> 每条给出代码位置、具体触发条件、预期与实际、影响、最小修正方向、是否必须在 MCP 服务层施工前修复。已实测者给出复现命令/argv/cwd/exit 与输出指针；纯静态推断已注明。**本轮探针未采集子进程 PID**（脚本未记录），需要 PID 的复现可用同一脚本重跑并在 `subprocess.run` 处补 `p.pid`；解释器与 cwd 已固定如上。

### P0

无。未发现能让"未发布/被篡改证据"在**已启用校验的路径**上被当作合法结果的缺陷。

### P1-1 `load_run` 以 summary 内的 schema 字段决定是否校验，单个字段即可关闭全部完整性检查

- **位置**：`src/ai_code_quality/runs.py:76`（首次 `if summary.get("artifact_schema_version") == 2:`）、`runs.py:99-103`（第二次同样的判断）
- **触发条件**：一个已正常发布的 schema2 run（`.complete.json` 仍在），把 `summary.json` 的 `artifact_schema_version` 改为 `3`、改为字符串 `"2"`、或**删除该键**，再改动 `findings.json`。
- **预期**：`runs.py` 的契约是"schema2 加载验证发布与摘要"（`core-implementation.md:10`），标记存在即应校验；未知/缺失 schema 应拒绝或降级为"未验证"。
- **实际**：三种改法都使 `verify_publication()` **完全不执行**；`cq gate` 把伪造的 blocker 当作真实结果采纳（`forged=True`），exit 1 并给出评级/checks。
- **影响**：这是**一次单字段改动即可关闭整个证据链校验**，不需要重写任何摘要，因此不属于"有权限者重写所有摘要"的免责边界，而是典型的"普通意外修改/半恢复/字段类型漂移"可触发路径：
  - 从旧备份恢复 `summary.json`（旧版本没有该键）→ 该 run 被当作 legacy，`findings.json` 即使已变也不校验；
  - JSON round-trip 丢未知键、或未来写 schema `3` 的 run 被旧读取器读到时**默认放行**（非 fail-closed）；
  - `cq gate`/`cq diff`/`cq suppress`/`cq baseline` 全部经 `load_run`，都会消费未验证证据并给出结论。
  MCP 层按设计会自己检查 marker 是否存在（因此**存在第二道防线**），但核心这一层"共享证据原语"的保证是失效的，MCP 一层的实现稍有遗漏就会直接暴露。
- **最小修正方向**：判定依据从"summary 字段"改为"标记是否存在"，并让未知版本 fail-closed：
  ```python
  marker = run_dir / ".complete.json"
  if marker.is_file():
      # 有标记一律校验；verify_publication 内部已校验 schema_version == 2
      verify_publication(run_dir, run_dir.name)
  else:
      schema = summary.get("artifact_schema_version")
      if schema is not None:            # 自称 schema2 却无标记
          raise RunNotFoundError("RUN_NOT_READY", ...)
      # 才是 legacy
  ```
  同时把 `artifact_schema_version` 存在但不等于 `2` 视为 `INVALID_ARTIFACT`（不是"当作旧 run"）。
- **是否必须在 MCP 服务层施工前修复**：**是**。MCP 的 `RUN_NOT_READY` / `INVALID_ARTIFACT` / `publication=verified` 契约直接建立在这个判定上。
- **证据（已实测）**：
  - 对照（未改 schema，仅改 findings）：`gate` → exit 3，`{"code":"INVALID_ARTIFACT","message":"…Published artifact changed: findings.json"}`（探针 B1，PASS）
  - `artifact_schema_version=3` → `gate` exit 1，采纳伪造 finding（探针 C[int3]）
  - `artifact_schema_version="2"` → 同上（探针 C[str2]）
  - 删除该键 → 同上（探针 C[absent]）
  - 复现：`cwd=<work>\probe\pC_int3`，`python -m ai_code_quality.cli gate --project . --run runC --format json --no-save`；输出指针 `evidence\probe-results.json` 中 `C[int3]/C[str2]/C[absent]`。
  - 标记未变、`cq gate` 仍能读到伪造 finding，说明**不是** marker 失效导致，而是校验被跳过。

### P2-1 Windows 大小写别名：同一 run 换大小写引用被判为"证据不符"

- **位置**：`runs.py:54-56`（`exact = root / run_ref`，直接以调用方书写的大小写返回）、`runs.py:96-98` 与 `runs.py:80/103`（以 `run_dir.name` 作为 run_id 比对）
- **触发条件**：run 目录为 `audits\casecheck`，调用 `cq gate --run CASECHECK`。
- **预期**：设计 §3 要求"Windows 文件系统大小写别名经实际路径规范化，不据不同大小写创建两个身份"；同一目录应解析为同一 run。
- **实际**：exit 3 + `INVALID_ARTIFACT: Completion marker identity/schema does not match`（把**正常 run** 报成**证据被篡改**）。同时 `prefix` 匹配（`d.name.startswith(run_ref)`）是大小写敏感的，exact 分支却大小写不敏感，两条路径行为不一致。
- **影响**：Windows 专属；MCP 若把客户端回传的 run_id 直接转发（客户端可能大写化/规范化），会把有效 run 映射成**不可重试的证据类错误**。写入侧无此问题（已实测：`casecheck` 后再写 `CASECHECK` → `RUN_COLLISION`/exit 3，只产生 1 个目录，探针 K1 PASS）。
- **最小修正**：解析后以磁盘真实名称为身份——`run_id = run_dir.resolve().name`（Windows 上 `resolve()` 返回真实大小写）；`prefix` 比较用 `casefold()`（POSIX 仍区分大小写，需按平台分支）。
- **是否必须在 MCP 服务层施工前修复**：**是**（成本极低；否则 MCP 的错误映射会把"合法 run"报成"证据损坏"）。
- **证据（已实测）**：`cwd=<work>\probe\pD`，`python -m ai_code_quality.cli gate --project . --run CASECHECK --format json --no-save` → exit 3；目录实际名为 `casecheck`。输出指针 `evidence\probe-results.json` 的 `D1`。

### P2-2 run 读取路径未做归属校验：`../` 与 junction 都能读到 `audits` 之外

- **位置**：`runs.py:50-67`（`resolve_run_dir` 直接 `root / run_ref`，只有 `(exact/"summary.json").is_file()` 判断）、`runs.py:70-105`（`load_run` 从不校验 run 目录真实路径）；对比 `evidence.py:43-47`（`inside()` 已存在，`scan.py:73/75` 已用它保护写入与发布）
- **触发条件**：(a) `--run ../outside/evilrun`；(b) `audits\jlink` 是指向项目外目录的 junction（其内有 legacy 形状的 `summary.json`/`findings.json`）。
- **预期**：设计 §9"run 数据限绑定项目 audits；链接/junction 解析后校验真实归属"；spec CQ-MCP-02"拒绝越界…及链接逃逸"。
- **实际**：(a) exit 0、`passed: true`；(b) exit 0、`passed: true`。两者都读了 `audits` 之外的文件并给出质量判定。
- **影响**：核心自述边界未落实。MCP 侧会按设计校验 `run_id` 字符集（可挡住 `../`），但**junction 挡不住**——MCP 生成的 `audits/mcp-<uuid>` 若被换成 junction，MCP 的 run_id 校验仍然通过。写入侧是安全的：`audits` 本身为越界 junction 时 `scan` 正确拒绝（exit 3 `OUTSIDE_PROJECT`，外部目录零写入，探针 S2 PASS），说明缺的只是**读取侧**同样的 `inside()`。
- **最小修正**：`resolve_run_dir` 返回前 `inside(candidate, project_root/"audits")`，且要求 `run_ref` 满足 `validate_id` 的字符集（拒绝分隔符/点段）；`load_run` 再对 `run_dir` 做一次 realpath 归属校验。
- **是否必须在 MCP 服务层施工前修复**：**是**——建议在核心修；若决定由 MCP 层承担，必须在契约里写明"核心不保证 run 读取归属"，并纳入 T03 验收（当前 T03 已列 junction/大小写，但本批把它们当作已覆盖）。
- **证据（已实测）**：
  - (a) `cwd=<work>\probe\pE`，`gate --project . --run ../outside/evilrun --format json --no-save` → exit 0；
  - (b) junction 由 `cmd /c mklink /J audits\jlink <work>\probe\ext_evil` 建立（rc 0），`gate --run jlink` → exit 0；输出指针 `evidence\probe-results.json` 的 `E1`、`F1`。

### P2-3 脱敏未贯穿全部落盘/输出通道：`inputs.json`、`scan --format json` 正常 stdout、`inputs` stdout

- **位置**：`scan.py:114-116`（`atomic_json(run_dir/"inputs.json", {...})` 未经 `redact_obj`）、`cli.py:807-808`（`print(json.dumps(out.summary…))` 未经脱敏）、`cli.py:834-836`（`inputs` 直接打印原始清单/摘要）
- **触发条件**：项目内存在文件名本身形如已知凭据的源文件（例：`sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX.py`，人工构造，未读真实凭据）。
- **预期**：本批既有实现已对 `summary.json`、`findings.json`、`report.md`、md 控制台、错误 envelope 脱敏（`report.py:26`、`scan.py:207-214`、`cli.py:814-822`），`REDACTION_RULES_VERSION=2`；同一条串在 `inputs.json` 与 json stdout 中却保持原文。
- **实际**：`inputs.json` 命中原文 `True`；`redact_text()` 对同一串返回 `'***REDACTED***.py'`（说明规则本身能识别）；`scan --format json` 的正常 stdout 同样命中原文——实测落在 `scanned_targets[1]`，且是**绝对路径** `…\sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX.py`；`summary.json`/`report.md`/`.complete.json` 未命中（已脱敏或本就不含该字段）。
- **影响**：本批把 stdout 变成 MCP 的**权威证据通道**（`--no-save` + design §7"保存完整合法脱敏 stdout"），但核心自身的成功路径 stdout 不脱敏、失败路径脱敏——这个不对称会让"MCP 已脱敏"成为唯一防线；`inputs.json` 是唯一未过 `redact_obj` 的发布依赖文件，与"五件套统一过规则"的表述不符。注意：`inputs.json` 只含**项目内相对路径**（探针 S4 PASS，无绝对路径），泄露面限于用户自己的文件名，故定 P2 而非 P1。
- **最小修正**：`atomic_json(run_dir/"inputs.json", redact_obj({...}))`；`_run_scan_command` 打印前 `redact_obj(out.summary)`；`_run_inputs_command` 输出前同样处理（或明确文档化"stdout 原件不脱敏、由 MCP 负责"，并在 MCP 层加必测用例）。
- **是否必须在 MCP 服务层施工前修复**：**是**（必须明确归属并落一条测试，不能两层都假设对方做）。
- **证据（已实测）**：`cwd=<work>\probe\pR`，`scan --project . --adapters ruff-check --run-id runR --format json` → 在 `audits/runR/inputs.json` 中命中原文；stdout 命中原文；输出指针 `evidence\probe-results.json` 的 `R1`、`R3`（`R2` 证明错误 envelope 已脱敏/结构化）。

### P2-4 `effective_adapters` 记录的是"选定列表"而非"实际执行集合"

- **位置**：`scan.py:106`（`"effective_adapters": [adapter.name for adapter in adapters]`）
- **触发条件**：`scan --adapters deepsec --no-deepsec`（`no_deepsec` 在 adapter 内部生效：`adapters/deepsec_adapter.py:134`）。
- **预期**：设计 §3 要求"每次返回实际 selected/not_selected"；§7 把 `effective_adapters` 列为可比性输入。
- **实际**：`effective_adapters=['deepsec']`，而 `tools[].status={'deepsec': 'skipped'}`——字段声称"有效"，实际未执行。
- **影响**：MCP 的 `declared_scope`/`selected_tools_complete`/comparability 若直接消费该字段，会把"被策略跳过"算成"已执行且完整"；虽然 `config.no_deepsec` 也在快照里（`config.py:118-120`），可比性仍能通过配置差异发现，但语义字段本身是错的。
- **最小修正**：分两字段——`configured_adapters` 与 `executed_adapters`（由 `results` 反推，`status in ("ok","error","timeout")`），或至少把被 `no_deepsec`/无配置跳过的排除出 `effective_adapters` 并另设 `not_selected` 说明。
- **是否必须在 MCP 服务层施工前修复**：**否**（可在 comparability/declared_scope 实现前修）；但在那之前**不得**在 MCP 里把该字段当作实际执行集合。
- **证据（已实测）**：`cwd=<work>\probe\p3`（即 `probe3\eff`），`scan --project . --adapters deepsec --no-deepsec --run-id d --format json` → exit 0，`effective_adapters` 与 `tool_status` 如上述；指针 `evidence\probe3-results.json` 的 `S3`。

### P3（不阻断，可后移；逐条给出理由）

1. **输入监视期限未进入任何证据**：`scan.py:54/83/97` 使用 `inputs_timeout_seconds`，但 `summary`/`config.snapshot()`（`config.py:106-121`）都不记录该值，也没有 `deadline_source`/总期限。两次仅在清单预算上不同的扫描产物无法区分。建议在 summary 增记，或由 MCP 台账记录并在 run_header 回填。
2. **`cli.py:796-805` 的 `FileNotFoundError` 分支已死**：`except OSError` 在前（`FileNotFoundError ⊂ OSError`），第二分支只剩 `ValueError` 可达；作者原意（项目目录消失 → exit 1）被改写为 `IO_ERROR/4`。影响仅限"`is_dir()` 检查后目录被删"的竞态，且新行为更贴近 IO 语义，故列 P3；建议删除死分支或调整顺序，避免误导后续维护。
3. **`runs.py:103` 的第二次 `verify_publication` 未包成 `RunNotFoundError`**：同一"摘要失配"条件，第一次（`:80-82`）抛 `LookupError` 子类，第二次抛 `EvidenceError`（`ValueError` 子类）。`.code` 一致，CLI 映射无碍；但按异常类型分派的调用方会漏判。建议与第一次一致地包装。
4. **`raw/coverage.json` 的"最终字节"其实被重写**：`scan.py:117-120` 用 `read_text`/`atomic_text` 重写，注释称"publish its final bytes"，但通用换行会归一化（CRLF→LF）、整文件进内存、非 UTF-8 会中止整次扫描（fail-closed）。建议改为字节级临时文件 + fsync + `os.replace`，或原地 fsync 后直接摘要。
5. **无目录 fsync**：`evidence.py:86` 只在文件上 fsync 后 `os.replace`，POSIX 下 rename 的持久性还需父目录 fsync。属已声明边界（不承诺断电事务）；且失效方向是"标记有、数据 rename 丢失"→ 校验失败（fail-closed），不会把混合证据当合法，故 P3。Windows/`os.replace` 语义为静态推断，未实测。
6. **标记本身无自摘要**：发布后向 `.complete.json` 追加一个字节仍能被接受（探针 G[.complete.json] exit 0）。这不是缺陷——标记的语义字段（schema/run_id/files）都被校验，改写它们属免责边界；但 MCP 不应假设标记字节稳定，也不要把它当"签名"。
7. **半写 run 与"不存在的 run"不可区分**：`resolve_run_dir` 要求 `summary.json` 存在，因此"超时中断留下的 `audits/<id>/raw/`"被报为 `RUN_NOT_FOUND`（探针 I2：`gate` → "找不到 run"），而不是 `RUN_NOT_READY`。建议 exact 命中已存在目录但无 summary/marker 时给 `RUN_NOT_READY`。
8. **`prefix` 匹配大小写敏感**（见 P2-1 附带）。
9. **32k 文件已贴近默认 60s 期限**：我自建 3,000 文件实测 summary-only 4.0s（≈1.3ms/文件，推算 32k≈42s），作者 32k 墙时 58.9–66.6s（含调用方读/解析）。默认每阶段 60s 对大仓只有约 1.5 倍余量；超时即 `INPUTS_TIMEOUT`/exit 2 且**无 marker**，表现为扫描整体失败。建议在文档与 MCP 默认值上给更大余量，或补一条 10 万文件/更慢磁盘的证据。
10. **`inputs.json` 体积与重复哈希**：完整清单前后两份（32k ≈ 18.6MB）；`load_run` 每次调用 `verify_publication` 两次，`gate` 又会 `load_run` 两次（`run_gate` + `cli.py:649`），约 4 次全量哈希。当前规模可接受；MCP 分页时建议提供"身份快检"与"全量校验"两档接口，否则每页都重哈希大清单。
11. **`.gitignore` 子集限制**：`targets.py:218-220` 忽略 `!` 否定且不读嵌套 `.gitignore`，`monitor_inputs` 与 `resolve_targets` 用同一子集（因此"监视集合"内部自洽），但与 ruff/pytest 的真实忽略语义不同；已在 `monitor_scope` 声明为"监视集合"而非分析器全集。属已披露限制，建议在 MCP 文档重复一次。
12. **文档未随 CLI 面更新**：新增 `inputs` 子命令、`scan --run-id/--inputs-timeout-seconds`、`gate/diff --no-save` 只在 `--help` 可见；proposal 的 MODIFIED 表列了 README/agent-adapters README，本批未做。属文档缺口，不阻断服务层。

---

## 4. 作者证据与统计的独立复核

| 作者声明 | 我的复核 | 结论 |
|---|---|---|
| 214/214 通过，0 fail/0 error/0 skip | 复跑 214/214，exit 0；33 项证据用例 33/33 | **成立** |
| ruff / format / mypy 通过 | ruff exit 0；format exit 0（60 文件；`src tests` 恰 56，与作者口径一致）；mypy 31 源文件 0 问题 | **成立** |
| 测试解释器未装 mcp | `core-facts…json` 记 `test_interpreter_has_mcp=false`；本机同样解释器亦无 mcp | 记录成立（未据此推断产品依赖） |
| 最终自扫 `cq-mcp-core-20261025-02` schema2 标记可核验 | 用候选 `verify_publication` 直接校验包内该目录 → 通过；`-01` 亦通过；旧 run 正确 `RUN_NOT_READY` | **成立** |
| 7 工具 ok、import-linter skipped | `tools` 实际：ruff-check/ruff-format/mypy/radon/vulture/pytest/deepsec = ok，import-linter = skipped，`scan_consistency=consistent` | **成立**（"不能说 8 工具全过"的口径正确） |
| 覆盖率 2733/3321 = 82.29448961156278% | 从 `raw/coverage.json` 复算：`2733/3321 = 0.8229448961156278`；gate 记录 `82.29448961156278` | **成立**（分子/分母与原始精度一致） |
| `--no-save` 后全文件 SHA256 不变、无新增 | 作者 `no_save_all_files_unchanged=true`；我另测 `gate/diff --no-save` 不产生 `gate.json`/`diff.json`、标记摘要不变（作者用例 33 项之一，我复跑通过）；并验证**不带** `--no-save` 时旧写盘行为保留（探针 X4） | **成立** |
| 六处写入点中断均不发布 | 复跑 6 参数用例通过；另用**真实**期限超时路径确认"目录残留但无 marker"（探针 I2） | **成立**（真实崩溃仍未测，见 §2） |
| 32,000 文件：9,312,754 字节、摘要 743 字节、120s 复测通过 | 两组独立输出均 9,312,754 字节、32,000 条、summary 743 字节；**复算 `object_digest` 与文件内、summary 内三者相等**；自建 3,000 文件 full/summary 摘要相等（372,814 B / 803 B） | **成立**（未重跑 32k 夹具本身） |
| Windows/WSL 锁、SDK、VS Code 仅为原型 | 未升级为产品/跨平台/客户端结论；本文未据此判断 | 记录口径正确 |

### 4.1 全量 A 门 exit1 的归因核查（独立）

- **新增 blocker 的具体位置与内容**：`deepsec:hardcoded_secret_database_url` @ `src/ai_code_quality/redact.py:39`。我读候选文件第 39 行：`    # 连接串里的密码：postgres://user:pass@host` —— 是**注释里的占位示例**，`user:pass` 为文档占位符，不是真实凭据。作者的"既有规则误报"判断**由内容独立证实**，不是仅凭作者陈述。
- **为什么表现为"新增"**：`schema.py:42-44` 的 `make_id(source, rule, file, line, message)` **含行号**；我实测同一 source/rule/file/message 在 line=37 得 `a66a2892c00a…`，line=39 得 `e4e3a7c0ddc9…`，与基线文件（line 37，`a66a2892…`）和本次 run（line 39，`e4e3a7c0…`）完全对应。
- **为什么豁免没接住**：HEAD 的 `.cq/suppressions.json` 两条记录**只有 id、没有 sig 字段**；`suppress.py:66-68` 对无 sig 的旧条目返回 `None`，`:86-90` 的签名集合因此为空 → 行号漂移后 id 不匹配，`scan` 侧 `_find_suppression` 直接返回 `None`。作者的"原登记仅有 ID，因此失配"**机制成立**。也印证 `suppress --reapply` 对这两条**无效**（无 sig 可对齐），只有重新以 `--finding/--action/--reason` 写入（会带 sig）才能根治——这是登记决策，属用户/作者权限，本轮未改。
- **另一个新增项是否属实**：`radon:mi-C @ cli.py`，我实测 MI：HEAD `cli.py` = **B (11.67)**，候选 = **C (7.47)**，与 gate 记录的 `7.4695450626601625` 同量级。这是本批新增约 70 行（`_command_error`/`_run_inputs_command`/错误映射）造成的**真实低危回归**，不是误报；它只出现在 `next_steps`，**不参与任何 gate check**（checks 中 `blockers` 失败只因上一条 blocker）。
- **是否妨碍进入下一阶段**：**不妨碍**。A 门唯一的失败项是"同一历史误报被行号漂移重新暴露"，不是本批新引入的安全/可靠性缺陷；但由此有三条必须写清的结论：
  1. 本批**不能**报"门绿"，作者也未这样报（口径正确）；
  2. 任何在该注释之上再插行的改动都会**再次**把它顶成"新增 blocker"，登记不重对齐就会反复红；
  3. 不能因为"作者认为是误报"就自动豁免——本轮也没有修改登记去换绿门。

---

## 5. 已有测试（33 项）的盲区与最有价值的遗漏反例

33 项本身质量不低：覆盖了标记缺失/损坏（4 种）、findings schema（3 种）、六处写入中断、coverage absent 与"事后出现"、碰撞不改旧字节、输入新增/删除/配置变化的摘要稳定性、显式空 adapter（API+CLI）、非法 run id（5 种）、`--no-save` 不写盘、读写失败 exit4、扫描期改动→unstable。**但它主要验证的是实现自身的假设**，以下边界没有覆盖（括号内为我本轮是否已实测出问题）：

1. **schema 降级/未知版本**（P1-1，已复现）——最该补：把 `artifact_schema_version` 改成 `3`/`"2"`/删除，断言拒绝。
2. **发布后篡改 `report.md` / `inputs.json` / `summary.json`**（我实测三者均正确报 `INVALID_ARTIFACT`，但测试只覆盖 `findings.json` 与 coverage）——属于"摘要覆盖五件套"的声明，应在测试里逐项固化。
3. **coverage 存在的发布→校验→gate 正路径**（我实测通过，S5），现有测试只测 absent 和"出现"。
4. **run 读取归属**：`../` 与 junction（P2-2，已复现）。
5. **Windows 大小写别名读取**（P2-1，已复现）与写入侧（已通过，K1）。
6. **脱敏端到端**：只有一条 Bearer 单测；没有"scan 产物中已知凭据被替换"的断言，也没有 stdout/inputs.json 的断言（P2-3）。
7. **并发**：`test_collision_never_changes_existing_bytes` 是**顺序**两次；没有 4 进程同 run-id 的并发负控（我实测 1 成功 + 3 `RUN_COLLISION`、无 `.tmp` 残留，N1）。
8. **`after` 监视阶段失败**：`test_inventory_failure_has_no_completed_scan` 让两次 `monitor_inputs` 都在 `before` 就抛；没有"artifacts 已算出、`after` 失败"的用例（代码上同样不发布，但未固化）。
9. **`inputs --summary` 与全清单摘要相等**（我实测 I3）、**`inputs` 全清单不含绝对路径**（S4）——这两条是 MCP 直接依赖的性质。
10. **期限边界**（0/601 在 CLI 层；我实测 K2/K3 均 exit 3 且不建目录）。

最小补测建议（按性价比排序）：先补 1、2、4、5（都是"证据身份"类，直接决定 MCP 能否信任核心），再补 6、7。

---

## 6. 三分：产品缺陷 / 证据或文档缺口 / 可后移改进

**产品缺陷（本批代码，需修）**
- P1-1 schema 字段决定校验（`runs.py:76/99`）
- P2-1 大小写别名误拒（`runs.py:54-56/96-103`）
- P2-2 run 读取未校验归属（`runs.py:50-105`）
- P2-3 `inputs.json` 与 json stdout 未脱敏（`scan.py:114-116`、`cli.py:807-808/834-836`）
- P2-4 `effective_adapters` 语义（`scan.py:106`）
- P3-1…P3-11（见 §3，除文档类）

**证据或文档缺口（不等于实现错误，但影响可核验性）**
- 真实 32k 夹具未随包（无法独立重跑，只能复算记录）；真实强杀半写未测（只有 monkeypatch 与期限超时两条路径）。
- `inputs_timeout_seconds` 未记录（P3-1），导致"清单预算"不可追溯。
- 新增 CLI 面未写入 README/agent-adapters README（proposal 已列但本批未做）。
- 正式 `.cq` 两条旧豁免无签名，且本批未（也不应擅自）重对齐；A 门红的原因需要在发布说明里写清"是同一历史误报 + 行号漂移"，否则外部读者会误读为新增安全缺陷。
- 六处写入中断是**注入式**负控，不是真实崩溃；`atomic_text` 的目录 fsync 缺失未在证据里标注为已知边界。

**可后移改进**
- `effective_adapters` 语义拆分（P2-4）可放到 comparability 实现前。
- 半写 run 的 `RUN_NOT_READY` 区分（P3-7）、`coverage.json` 字节级发布（P3-4）、目录 fsync（P3-5）、标记自摘要（P3-6）、prefix 大小写一致（P3-8）。
- 32k 以上的清单规模与期限默认值（P3-9）、`inputs.json` 体积与重复哈希（P3-10）、`_Gitignore` 子集说明（P3-11）。
- `cli.py` 的 MI 回归（B 11.67 → C 7.47）：建议在下一次 CLI 边界整理时拆分 `_run_scan_command`/错误映射，属低危技术债，不影响 MCP 服务层。

---

## 7. 本批不能声称的内容与我看到的残余风险

- 不能声称"MCP 已可用/九工具已实现/台账与锁已实现"——包内 `manifest.json` 自述 `mcp_service_implemented=false`，`tasks.md` 的 T01–T28 未勾选，与事实一致。
- 不能声称"发布已通过"——A 门 exit 1，正式 `.cq` 未改；本文件也不是发布验收。
- 不能声称"跨平台已验证"——Windows 之外全为静态推断；WSL/锁/VS Code 源码核查都不是产品恢复或客户端验收。
- 不能声称"任意秘密都能被发现"——本批只加了 `Bearer` 一条已知形态（`redact.py:17`，`REDACTION_RULES_VERSION=2`），且明确不承诺高熵串；`Authorization: Basic …` 等形态仍未覆盖，属已披露限制。
- 不能把"两次摘要相同"当文件系统原子快照：`monitor_inputs` 用 `st_size`+`st_mtime_ns` 前后各一次 stat 来检测读取期间变化（`targets.py:157-166`），读完后到 `after` 之间仍有窗口；`monitor_scope` 已声明为"监视集合"，设计也承认不承诺原子快照。这是**已声明**的边界，不是隐藏缺陷，但 MCP 的 `scan_consistency=consistent` 文案不得表述为"文件未被修改"。
- 残余风险（未消除，需在 MCP 层或后续批次处理）：junction 读取逃逸（P2-2）、脱敏归属（P2-3）、schema 降级（P1-1）、大小写别名（P2-1）；以及"有权限者重写 marker 与数据"这类明确免责的场景。

---

## 8. 结论（三选一）

**修复列明问题后可进入 MCP 服务层。**

理由（只谈本批正确性，不用"架构成立"替代）：

1. **可以进入的正面依据**：发布协议的关键性质经我独立实测成立——写入顺序为 `inputs.json → coverage（若有）→ summary → findings → report → 摘要全部依赖 → 最后原子写 .complete.json`；标记包含五个依赖（缺 coverage 记 `absent`）且 `verify_publication` 对每个依赖重算摘要；标记在依赖定稿后才写，失效方向是"标记有、数据不符 → INVALID_ARTIFACT"（fail-closed），不会把混合证据当合法；真实期限超时与并发同 run-id 都验证为"1 个赢家 + 无 marker 残留/无 `.tmp`"；运行 ID 校验在**建目录之前**完成（5 种非法输入均 exit 3 且不建 `audits/`）；`inputs` 全清单与 `--summary` 摘要严格相等、路径为相对、`rules_version`/13 个配置逐项 absent 均落实；作者 214/214、33/33、82.29448961156278%、32k 清单统计与 A 门归因均可复算成立。
2. **不能直接进入的原因**：P1-1 使"schema2 必校验"这一条**当前不成立**，而它正是 MCP 判定 `publication=verified` / `INVALID_ARTIFACT` / `RUN_NOT_READY` 的基础；P2-1/P2-2 分别会把合法 run 报成证据损坏、把 `audits` 外的 run 当合法读取；P2-3 让"脱敏"在核心与 MCP 之间有归属空档。这些都不是"架构问题"，是**本批实现的正确性问题**，且修复成本低（均为数行到十余行）。
3. **进入条件（建议作为下一批的入场检查）**：
   - 必修：P1-1、P2-1、P2-2、P2-3；P2-4 若不在本批修，必须在 MCP 契约中写明不得把 `effective_adapters` 当实际执行集合。
   - 必测：为上述四项各加一条负控（含本文 §5 的 1/2/4/5/6/7）。
   - 必写：`inputs_timeout_seconds` 的追溯方式、stdout 脱敏归属、A 门红的归因说明。
   - 不得：以修改正式 `.cq` 登记或降低阈值来换绿门；不得把本轮意见写成发布验收通过。

本文件不评价另一位审核者，不修改实现，不构成发布验收。
