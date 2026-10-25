# cq MCP 冻结设计审阅

## 1. 总体判定

**有条件可实施**。首发范围克制、run ID 扩展方向正确、质量结论与完整性分离的契约清晰。存在一项核心语义缺口（findings 过滤契约与统一 envelope）、一项锁与路径约束的可绕过风险、一项任务终态判定循环，须在实施时修订。

## 2. Findings

### F1｜严重｜spec CQ-MCP-08 + design§4 表 vs. runs.py 现状
**冲突证据**：design 表格规定“gate exit 1 / diff exit 1 → ok=true / isError=false，有效质量失败不当启动错误”；CQ-MCP-08 强调 core exit 与 MCP transport 分离。但统一返回示例中 `"ok": true, "cq_exit_code": 1` 且 envelope 只有一层 `ok`，gate/diff 的 core 质量失败（exit 1）与工具调用成功共享同一信号。客户端无法在不 parse 嵌套 `data.core_gate` 的情况下区分“调用成功但服务判定失败”与“MCP 工具失败”。现有核心 gate exit 1 是业务语义，MCP 工具结果必然同时携带 `ok:true`，导致依赖 `isError=false` 的客户端把质量不过当常规成功处理——契约本身自相矛盾。
**触发**：任一 gate 返回 exit 1，观察者的错误处理路径不会触发，需人工读 data.core_gate。
**影响**：质量门结果静默通过自动化编排。
**最小修订**：在 spec/design 中明确工具级 `ok` 只描述可获得领域结果，另设 MCP 工具返回字段 `assessment`（fail/pass/cannot_judge）为一级结果信号，或明确把工具级 isError 定义为质量失败。不要靠嵌套字段兜底。
**验证**：T09 增加“客户端对 exit=1 能区分调用成功与质量失败”的断言。

### F2｜严重｜design§5 去重范围 vs. CQ-MCP-05
**冲突证据**：design 说“去重范围为规范化项目根与状态目录，重启仍有效。另一个状态目录不共享去重，但必须共享项目锁”；CQ-MCP-05 要求“相同 request_key 和规范化参数重复提交返回原 job”，“相同真实项目根在多个 MCP 进程间最多一个执行型操作”。若两个 MCP 实例使用 **不同 state-dir** 绑定同一项目，各自台账不共享，但锁在同一 `<project>/audits/.cq-mcp-lock/`。第二个实例有相同 key 时因台账缺失而新起 job，随后被锁挡为 PROJECT_BUSY，于是对同一 key 返回“新 job 但忙”而非“原 job”。同一逻辑请求在不同 state-dir 下产生两个 job_id，违反“同一 key 同参数必返回原 job”。
**触发**：两个客户端以不同 state-dir 连接同一 project，先后提交相同 request_key。
**影响**：去重契约失效，并暴露 job 台账与项目锁分属不同命名空间的设计裂缝。
**最小修订**：去重键必须包含跨 state-dir 共享的跨进程锁名（如项目根+request_key 哈希），或明确“多 state-dir 同 project 不提供跨台账去重，仅锁互斥”，并降级 CQ-MCP-05 该条为单 state-dir 约束。后者更贴合本地单用户。
**验证**：T05 增加“两个 state-dir 同 project 同 key 的返回一致性”用例。

### F3｜高｜design§6 + MODIFIED scan.py “run_id 限定位于 audits 下”
**冲突证据**：proposal MODIFIED 与 CQ-MCP-06 承诺核心新增可选 run_id、原子独占建目录；design§6 要求“resolve 后校验位于项目 audits 下”。但冻结源码 `scan.py` 的 `run_dir = root / "audits" / run_id` **未 resolve 每个组件**，且当前无 run_id 参数。设计声称适配层能解决，但核心改造本身必须包含“run_id 经 path 校验后仅作单级目录名拼接”的写死实现。现在规格只说“resolve 后校验”，没有规定核心是否 reject 含 `..`/分隔符/绝对路径的 run_id。若核心只做字符串拼接，MCP 传的受限 run_id 仍可能在未来被其他 CLI 调用绕过。
**触发**：未来 CLI 用户传 `--run-id ../../x`，或 MCP 适配继承旧路径处理。
**影响**：可写入 audits 外，破坏 CQ-MCP-02 的 OUTSIDE_PROJECT 承诺。
**最小修订**：在 MODIFIED 中明确核心 scan 新增的 run_id 校验必须拒绝路径分隔符与 `..` 后才拼接，且 `mkdir(exist_ok=False)` 失败返回非零。不要把路径安全全部留给 MCP 适配层。
**验证**：T03/T06 增加“CLI --run-id 越界直接失败”核心级测试，不只测 MCP 层。

### F4｜高｜CQ-MCP-07 + design§5 cancel 状态机
**冲突证据**：design 规定“cancel 请求不能立即把仍活着的任务标为 cancelled”，CQ-MCP-07 要求“仅确认回收后可报告 cancelled/timed_out”。但 design 工具表 `cq_job_cancel` 返回“state=cancellation_requested”，状态枚举只有 `cancelled` 无 `cancelling`。当客户端 cancel 后立刻调用 `cq_job_get`，可能读到 `cancelled` 但进程仍活着；或读到 `cancellation_requested` 而状态枚举不包含该值。状态字面量与判定循环未定义。
**触发**：cancel 后无等待地查询 job。
**影响**：客户端可见不一致终态或未知状态值。
**最小修订**：把 `cancellation_requested` 定为状态机的合法中间态（或显式增加 `cancelling`），并明确 get 可返回它直到回收完成。禁止 get 把 `cancelling` 报告为终态。
**验证**：T07 增加“cancel 后立即 get 的合法状态序列”断言。

### F5｜中｜design§7 cursor 完整性 vs. CQ-MCP-09 分页
**冲突证据**：cursor“包含过滤条件、offset、文件 digest”；CQ-MCP-09 要求“分页中途文件变化必须失效”。但 design 只说“文件变化返回 STALE_CURSOR 或 INVALID_ARTIFACT”，没有规定 cursor 是否绑定 **findings 文件身份独立于 summary**。若 `findings.json` 内容变而 summary 未变（例如外部进程替换 findings），cursor 只带 summary digest 将无法检测，可能导致分页拼接出混合版本。
**触发**：扫描完成后外部改写 findings.json 内容但保留 summary.json 不变。
**影响**：STALE_CURSOR 漏检，分页数据跨越两个来源不真实。
**最小修订**：明确 cursor 或每次分页读取时独立记录 findings.json 的 SHA256，与 cursor 内 digest 强绑定。
**验证**：T12 增加“仅改 findings 内容导致游标失效”用例。

### F6｜中｜spec CQ-MCP-12 脱敏 vs. artifact 内容
**冲突证据**：CQ-MCP-12 要求“finding message/evidence 属不可信项目内容，不能被服务当指令执行”，且“MCP 返回与持久化诊断均不含原值”。但 `cq_findings_get` 需要原始 finding 的 message/evidence 呈现给客户端。若 message 中含疑似 token，按“不返回原值”会破坏 finding 字段；若返回，脱敏规则没有定义“哪些属于密钥、哪些属于正常 finding 文本”。契约未划清诊断输出与 finding 内容的不同脱敏标准。
**触发**：合法 finding 文本包含 API 密钥字符串，或真实错误诊断中夹杂 token。
**影响**：要么过度脱敏破坏报告，要么默认泄露。
**最小修订**：分别定义“诊断/异常/审计日志脱敏”和“finding 内容允许原样返回但标注不可信来源”，不把两者合并为同一脱敏规则。
**验证**：T15 拆两条：stderr/台账无 token；finding 原样返回但标记为项目内容。

## 3. 值得保留的设计

1. **start 不等待扫描、长任务用 job 查询**：不引入实验性 Tasks 扩展，贴合本地单机。
2. **MCP annotations 与真实权限分离**：readOnlyHint 只作提示，不参与权限判断，避免协议语义被误用。
3. **run ID 双侧身份验证 + 完整 run 枚举检查**：明确 MCP run 与旧时间戳 CLI run 分离，且读取时核对 run_id 与项目根，为路径约束打好基础。

## 4. 未验证项与证据限制

未实际执行扫描、测试、客户端连接或进程回收验证；SDK 版本、客户端兼容性、HTTP/MCP 协议细节均为待确认。本审阅仅依据冻结文档与提供的源码节选，不声称任何实现已满足。未提供源码的模块（diff/adapters/pytest）其内部状态与本审阅无关。所有对现有代码行为的判断来自片段，不构成执行证据。