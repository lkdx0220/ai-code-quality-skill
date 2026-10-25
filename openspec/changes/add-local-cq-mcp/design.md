# cq MCP 设计与接口契约（r03 / 实施前定稿）

DeepSeek与GLM均对r02给出静态“可实施”。r03落实复核中的默认/边界决定和文档补全，不声称两位已经审核r03或运行实现。本稿是实施依据，替代r02同名旧定义。

## 1. 架构与发布范围

用户电脑的 MCP 客户端 → 本地 stdio cq-mcp → 固定 argv 的 cq 子进程 → 现有分析器。CLI、Skill、DSH 继续可用，MCP 不复制扫描/评级算法。Python 官方 MCP SDK 为同仓可选 extra，核心 dependencies=[] 保留；入口定为 cq-mcp，实施时同步适配器 README 中未实现的 cq mcp 占位说明。

首版九个工具（原八个 + 只读 cq_runs_list），单受信项目、无 HTTP/远程租户、不自动安装、不开放代码修复和账本写操作。默认不运行 pytest；测试需用户启动配置启用且调用显式选择。SDK 精确版本/协议版本/客户端配置在实施前核查，不假设已兼容。

保留 Windows/Linux、两个真实客户端的发布验收，当前不因排期推测降低标准。先做 Windows 进程控制原型及客户端可获取性调查；若能力不可用，应单独修订发布范围并如实标未支持，不能用 mock 或 skip 顶替。首版不保证恶意仓库隔离，不把工具状态完整等同底层分析器检测无漏报。

阶段1候选实测SDK为mcp2.3.0（MIT），隔离安装于Python3.13.14；ClientSession/stdin-stdout原型协商2025-11-25，不能据此宣称已验证2026-07-28无状态协议或所有旧客户端。Python API用is_error/structured_content等snake_case，wire仍为isError/structuredContent；序列化必须用协议alias，不能照搬SDK1.x属性访问。Windows原型使用pywin32 312；若产品采用该绑定，应在mcp extra中直接声明Windows条件依赖，不靠偶然的传递依赖。确切发布依赖/支持协议须由后续双宿主和构建安装实测定案。

## 2. 启动、执行配置与时间预算

拟定入口：`cq-mcp --project <绝对项目根> --state-dir <绝对状态目录> [--tool-python <受信解释器>] [--allow-test-execution]`。

project 必须存在；state-dir 要在被扫描树之外。启动仅做参数/路径/小配置加载和环境快照，不执行 doctor、PATH 探测、git 或全库 hash。initialize + tools/list 在验收环境冷启动 <5s；异步事件循环不被子进程等待阻塞。

解释器选择采用明确的轻量规则：--tool-python > 启动 CQ_PYTHON > 项目 cq.toml/.cq.toml > 服务 sys.executable。只解析路径和记录来源，不自动遍历候选解释器；首次 doctor 检查该固定解释器，缺工具返回缺失，引导用户重启时显式指定其他解释器。每次 doctor/scan 传 --python，DeepSec 配置/子进程 env 同样冻结。项目执行配置变更返回 CONFIG_CHANGED；不输出完整环境。受信项目包含其执行配置，不能把此机制宣称为安全沙箱。

doctor为应用层job：cq_doctor快速提交kind=doctor，使用同一job_get/cancel；总期限600s。扫描默认3600s；启动参数--max-scan-seconds范围1..86400、默认3600，调用timeout_seconds范围1..该上限。新鲜度及扫描前后各一次输入监视期限由启动--inputs-timeout-seconds设定，范围1..600、默认60；传给核心inputs/scan，不能由调用方传任意CLI参数。gate/diff核心计算上限60s，回收宽限5s。扫描两次监视也计入扫描总期限，整体上限可早于工具预算耗尽。

gate/diff首版保留同步调用；verify_current仅校验目标run的一次工作区清单，基线只验证历史产物身份。默认最坏执行上限125s（60+60+5），最大配置665s；客户端工具调用期限须再留协议余量，建议至少上限+15s。文档提供两个真实宿主对应配置；T19必须验证长调用、断开后取消与子树回收。若真实宿主不支持所需时限，不能宣称支持该配置，须在核心扩展前修订接口或发布兼容范围。

记录实际 Config.timeout_for 值、最终总期限和 deadline_source。不能把 DEFAULT_TIMEOUTS 字典静态相加当实际预算：现源码 timeout_for 仅取 timeout_overrides 或 timeout_default；radon 有 cc/mi 两个调用，DeepSec 按层和目标多次执行。长扫描可能在核心预算尚未耗尽时被总期限终止；此时明确 timed_out/无结论，不推造 summary/findings。首版不做增量 findings 落盘。

## 3. 工具与输入

所有输入 object additionalProperties=false。run_id/base_run_id/request_key/job_id 为完整单级 ID：ASCII 字母数字/_/-，长度1..128；拒绝 Windows 设备名（不分大小写）、尾点/空格、冒号、绝对路径、分隔符和点段。run/base 字符集与核心 baseline 名称约束一致；Windows 文件系统大小写别名经实际路径规范化，不据不同大小写创建两个身份。

| 工具 | 参数（? 为可选） | 返回及副作用 |
|---|---|---|
| cq_doctor | request_key | 提交 doctor job；探测子进程，写服务台账，持项目锁；返回 job_id/reused |
| cq_scan_start | request_key, adapters?, timeout_seconds? | 提交扫描 job；写 audits/run、服务台账和缓存，测试条件执行 |
| cq_job_get | job_id | 状态、期限、退出码、错误、doctor 结果或扫描 run_header；仅读任务与审计日志 |
| cq_job_cancel | job_id | cancellation_requested(bool)、state、cleanup；终止归属进程树，终态幂等 |
| cq_runs_list | cursor?, limit?(1..50，默认20), include_legacy?(false) | 当前台账 job 和该项目具有完成标记 run 的分页发现索引（完整性尚待复算）；旧 run 可选显示 unverified，不自动认定完成 |
| cq_findings_get | run_id, severity?, status?, cursor?, limit?(1..100，默认50), verify_current?(false) | run_header、tagged items、total、returned、next_cursor |
| cq_diff | run_id, base_run_id, verify_current?(false) | 两侧run_header、历史core_diff、comparability/temporal_scope；写state快照 |
| cq_gate | run_id, target?(A), base_run_id?, verify_current?(true) | run_header、core_gate、verdict、范围/证据/理由；false可给明确历史判定；写state快照 |
| cq_artifact_get | artifact_id, offset?(0), length?(1..8192，默认4096) | 来源 run_header、脱敏文本块、next_offset、digest、media_type；历史快照不是当前代码结论 |

省略adapters时默认五项：ruff-check、ruff-format、mypy、radon、vulture。import-linter、deepsec只在调用显式选择时参与；pytest另须启动--allow-test-execution。省略的安全/架构/测试/覆盖率维度必须列入policy_out_of_scope，不能把默认结果称为“全部维度达标”。显式选定的可选工具一旦missing/no_config/skipped仍为runtime gap，不根据运行结果悄悄缩小范围。启动允许测试不自动选择pytest。显式空数组/重复值/策略外项拒绝；合法adapter集排序作幂等摘要。核心get_adapters(None)保留CLI旧默认；get_adapters([])、scan API显式[]及CLI空白/空串均报错，MCP总传显式非空列表。

一致性测试验证核心ADAPTER_NAMES恰为“默认五项 + 显式可选import-linter/deepsec + 受控pytest”，三组互斥，变化须重新决定策略。每次返回实际selected/not_selected。status过滤仅new/suppressed；旧run其他原值保留并在available_statuses披露，但existing/fixed/accepted不能当查询过滤。相对基线分类只在diff中解释。

所有工具都记录有界服务调用审计，annotations 保守统一 readOnlyHint=false，并明确实际目标业务写入范围；权限来自真正的策略校验，不依赖 annotations。

## 4. 返回层次、范围与最终判定

公共envelope：schema_version=1.2、operation、ok、cq_exit_code（未启动为null）、data、warnings、error。JSON text保底；协商支持时同时提供structuredContent；预算按整个序列化工具结果（包括两份内容和包装）计算，默认64KiB。outputSchema在SDK/两客户端核查后确定，须与实际成功/错误envelope匹配。

ok/isError 表示调用是否得到有效领域结果，不能表示质量是否通过。r02 用 verdict 替代旧 assessment，不同时保留两个权威质量字段。

- declared_scope：full、所选 adapter、目标 A/B、是否请求 baseline，policy_out_of_scope（例如 pytest 未授权、coverage 未选、未请求差量）。
- evidence：selected_tools_complete、publication=verified/unknown/incomplete、runtime_gaps、core_skipped_checks；刻意不选的能力放 out_of_scope，已选择却 skipped/error/timeout 放 gap。
- scan_consistency：consistent/unstable/unknown，记录扫描前后清单是否一致及当时时间，不能代表现在的工作区。
- freshness：current/stale/unstable/unknown，附checked_at、rules_version、monitor_scope；verified_now表示本次是否成功完成校验，verification_status为not_requested/verified/timed_out/failed。未请求本次检查为unknown，不沿用历史current。
- temporal_scope：current_workspace/historical_run/undetermined。历史判定另附scope_gaps，不能因为pass_historical隐去未测维度。
- reasons 为 `{code, detail, source}` 数组；所有 findings/列表/快照都携带同口径 run_header，不只 gate 有这些字段。

gate verdict 的确定顺序：
1. 无合法核心输出或产物身份/完整性校验失败：工具错误，不给质量 verdict。tools_ok=false是执行健康缺口，归第3步cannot_judge，不当质量失败。
2. publication非verified的旧run：cannot_judge，原报告仅历史展示。已验证run中，核心存在可信质量检查失败才给fail：限blockers/highs/complexity/coverage，以及基线可比且两侧已验证时的new_blocker_high；不含tools_ok。保留范围/新鲜度限制，只说明扫描版本发现失败。
3. 核心exit2、选定工具runtime gap、scan_consistency非consistent、或指定基线不可比：cannot_judge；不覆盖原core_gate。target B仅new_blocker_high失败且基线不可比时，也不得误判可信fail。
4. 核心通过、两次扫描输入一致且产物已验证，调用显式verify_current=false：pass_historical，freshness=unknown、verified_now=false、temporal_scope=historical_run，reasons含CURRENT_NOT_VERIFIED；scope_gaps照常保留。这只证明所存历史版本在声明范围的结果。
5. 已请求校验但超时/失败/不稳定：cannot_judge，reasons点名FRESHNESS_TIMEOUT或INPUTS_UNAVAILABLE，不能静默降为pass_historical。成功复算但摘要不同：pass_stale，仅历史通过。
6. 核心通过且freshness=current：有policy_out_of_scope/core_skipped_checks为pass_with_gaps，无这些限制才为pass。两者只在声明范围、监视集合、检查时刻成立。可信失败仍依第2步优先报告，不能被超时覆盖，但必须显示未完成当前验证。

默认五项正常、无质量失败、已验证当前输入且无baseline时为pass_with_gaps，即使未安装DeepSec/未配import-linter也成立，reasons列明未选择的安全/架构/测试等维度。显式选择DeepSec但缺失则cannot_judge。缺默认五项任一也不能通过。docs首页和工具描述各给这一对示例；不能把cannot_judge解释为服务坏了。

| CLI 结果 | MCP 映射 / job终态 |
|---|---|
| doctor 0/2 且合法 JSON | 调用结果有效，job completed；2=环境缺项，不等于就绪 |
| scan 0/2 且产物已发布并校验 | job completed；2=evidence gap，不给通过结论 |
| scan 1（原有用法错误）、新增scan 3（碰撞/显式空/ID错误）、scan/gate/diff/inputs写读产物IO失败4 | job failed或同步isError=true；按明确error.code映射，非质量失败 |
| scan 2但无发布标记且结构化INPUTS_TIMEOUT/INPUTS_UNAVAILABLE | job failed，无合法扫描结果；不能按exit2猜成completed。整体deadline超时仍为timed_out |
| gate 0/1/2 有合法报告 | isError=false/ok=true；由上述算法给 verdict；1为有效失败、2无法完整判断 |
| diff 0/1 有合法 JSON | isError=false/ok=true；原始新增问题结果保留；不可比时不作回归结论 |
| gate/diff 3 | isError=true，引用/配置错误；缺run映射RUN_NOT_FOUND，不能伪装cannot_judge |
| 未知退出码/JSON损坏/输出超硬上限 | CLI_ERROR/INVALID_OUTPUT/OUTPUT_TOO_LARGE，不能按数字1猜质量失败 |
| 总期限/取消/启动失败 | timed_out/cancelled/failed；未完成产物不能消费为扫描结果 |

--format json的新失败路径提供`{error:{code,message}}`，stderr仅脱敏诊断；正常领域报告schema不改写。产物写失败exit4优先于尚未成功返回的质量exit1/工具exit2，error可附underlying_exit_code但不伪造已发布结果；--no-save没有原run写步骤。doctor无项目产物exit4，MCP自身IO失败映射IO_ERROR。

本版完整工具error.code集合：INVALID_ARGUMENT、POLICY_DENIED、REQUEST_CONFLICT、PROJECT_BUSY、STATE_BUSY、STATE_PROJECT_MISMATCH、JOB_NOT_FOUND、RUN_NOT_FOUND、RUN_NOT_READY、RUN_COLLISION、INVALID_ARTIFACT、STALE_CURSOR、OUTSIDE_PROJECT、CONFIG_CHANGED、AMBIGUOUS_BASE_RUN、STATE_LIMIT、INDEX_LIMIT、CLEANUP_FAILED、CLI_UNAVAILABLE、CLI_ERROR、INVALID_OUTPUT、OUTPUT_TOO_LARGE、IO_ERROR、INPUTS_TIMEOUT、INPUTS_UNAVAILABLE。FRESHNESS_TIMEOUT/CURRENT_NOT_VERIFIED等为领域reasons.code，不与工具error混用；执行前错误/缺产物无verdict。实现须集中常量并做枚举一致性测试，扩充先改契约。

## 5. 锁、幂等与生命周期

state-dir使用SQLite保存任务、request_key唯一约束、artifact/cursor登记和瞬态容量reservation；一个state绑定一个规范化真实项目，不匹配报STATE_PROJECT_MISMATCH。请求摘要含operation、排序adapter、有效期限、冻结配置摘要。BEGIN IMMEDIATE短事务内：查重 → 验证并预留容量 → 非阻塞项目锁 → 插入job及唯一key → commit → 回应；任一步失败rollback释放本次预留/锁。事务等待上限5s，STATE_BUSY不能冒称去重成功。同台账多实例/线程持锁语义同时由进程内互斥与OS锁实现，不能依赖flock对同进程一定互斥。

扫描job在受理事务中预生成mcp-<UUID>完整run_id，以--run-id交核心。cq_scan_start返回job_id/run_id；spawn前job_get的run_state=pending、publication=incomplete、created_at=null，未建run目录；核心开始写后writing，验证.complete.json和依赖摘要后才published。pending ID不等于已有可读取结果。失败轮保留ID和实际目录状态，不重用目录。

任一终态使用同key同参都返回原job、reused=true、terminal_state及rerun_hint=使用新key；换key才重新执行。跨state-dir仅互斥、不共享幂等。项目忙的全新请求不落“已接受job”。进程崩溃发生于commit后spawn前时，恢复标interrupted，不偷偷重跑；SQLite恢复与任务状态需交叉验证。

项目执行锁移到同一OS用户的固定用户缓存命名空间：Windows为%LOCALAPPDATA%/cq-mcp/locks（缺该变量回退用户LocalAppData路径），POSIX固定用户home/.cache/cq-mcp/locks；不随state-dir或XDG_RUNTIME_DIR变化，也不开放调用级覆盖。键为规范化真实项目路径的SHA256，Windows统一大小写，路径别名解析到同一根。目录权限仅当前用户，锁文件稳定不删不重建，POSIX flock/Windows msvcrt.locking。需相同用户配置命名空间；跨OS用户、直接CLI及网络文件系统不保证串行，明确披露，不能称全机器全写入方互斥。

OS退出自动释放锁不等于子树已退出。用户锁旁owner/启动意图记录在执行前原子持久化，含pid+出生身份+任务域/state来源；跨state恢复也先看该记录。无法证明残留树已回收返回CLEANUP_FAILED；不能按旧PID杀进程、把缺owner记录直接当空闲。两实例并发首创锁文件须用不替换inode的open/create，记录损坏保守阻断。

doctor/scan全生命周期、gate/diff及显式inputs检查持执行锁；查询/cancel/列表不争锁。doctor会启动工具/插件探测，保留串行资源和残留归属保证；scan活动时doctor报PROJECT_BUSY，不承诺并行体检。docs推荐doctor完成后scan。只读项目根及audits也可gate/diff，前提用户锁目录/state可写，子进程不需项目缓存写入；不修改项目.gitignore。scan仍须audits可写，分析器自身缓存写入另披露。

状态 queued→running→completed/failed/cancelled/timed_out/interrupted/cleanup_failed。cancellation_requested为bool；queued取消要在spawn前再检查；running取消确认回收后才变cancelled。完成与取消用事务记录事实先后，已完成不可追改取消。cancel不等执行锁，循环必须能服务job_get；验收时这两者的受理返回<1s，不等子树实际回收。

Windows须在子进程执行用户代码前纳入Job Object（CREATE_SUSPENDED→assign→resume等经验证方式），所有CLI结束后都核查并回收残留后代，包括adapter单工具超时路径。Linux进程组用于正常取消/超时/EOF；服务被SIGKILL后不宣称自动回收整棵树，重启检测残留并阻止新执行直到确认清理；不能仅凭OS锁已释放就扫描。断电/存储损坏不能保证任务状态完整，宁可interrupted/unknown。T07/T08用真实进程验收这些平台区别。

Windows虚拟环境可能有python redirector中间进程；不得假设Job内恰好“一个CLI+一个工具”，也不能将Popen/CreateProcess的初始PID直接当最终Python PID。保存初始进程句柄/出生身份及真实任务域，回收按Job及活跃进程数归零验证，跨state恢复另验owner记录，不能仅凭本原型通过宣称恢复已实现。

## 6. 核心扩展与证据发布

本轮核心扩展已超出r01的“只加run-id”，须按proposal路径表一起审核：

1. scan --run-id、run_scan可选run_id；所有路径/summary/context引用一致；校验ID和父路径后原子mkdir外层run（exist_ok=false），后建raw。碰撞返回scan exit3、RUN_COLLISION；旧默认时间戳正常格式保留，但同秒覆盖改为失败，明确为行为修正。
2. 显式空adapter在CLI/API/注册表三层拒绝。仅None保留原默认，不允许`[] or cfg`泄漏成全量。参数和adapter先验证再创建run。
3. Config.snapshot纯增 enabled_adapters、no_deepsec、respect_gitignore；scan记录selected_adapters（effective_adapters为兼容的选定范围别名）、attempted_adapters（非skipped）、completed_adapters（ok）、skipped_adapters，以及实际tool版本、cq版本、配置文件与suppression摘要。选中但skipped仍是runtime gap，不能因未执行而缩小声明范围。旧字段不删。
4. targets.py提供唯一的输入监视枚举函数和rules_version；scan与新增`cq inputs --project ... --format json [--summary] --timeout-seconds N`共用。MCP固定--summary，只输出规则/范围/计数/配置摘要/完整monitor_digest（含路径、kind、哈希、absent、入口）；不经stdout传逐文件全集。默认完整CLI模式仍可输出全清单，MCP不使用。规范排序及canonical JSON/UTF-8序列化定义和共享函数由核心统一，避免两实现hash不同；不使用会受Python hash随机化影响的摘要。
5. 该清单明确为cq监视集合，不能称“分析器实际读取的所有文件”：工具自有exclude、pytest动态import和运行时数据可能不同。记录监视范围与不足；用共享规则fixture验证集合，不以ruff/pytest argv的目录参数假装逐文件等价。尊重核心排除规则，排除.env/缓存/审计/锁/state；不修改原有目标选择结果来迁就指纹。

输入规则v2：逐文件path为已知规则脱敏后的相对展示路径，path_sha256为原始相对路径UTF-8摘要，sha256仍为文件原字节摘要。两个路径脱敏后同名也不可合并；重命名须改变监视摘要。redaction_rules_version纳入规范数据，先形成可公开的脱敏结构再计算monitor_digest；复算时仅排除monitor_digest/files_count/checked_at。rules_version不同不可直接比较。项目外源文件链接使监视明确OUTSIDE_PROJECT失败，不静默漏项；root-only gitignore子集边界保留。
6. 新run summary标artifact_schema_version=2。写完summary/findings/report/inputs与可用coverage后，对这些门和证据依赖文件记录摘要；缺coverage也明确absent。每文件临时写+flush/fsync+原子替换；最后原子发布`.complete.json`，含run_id、cq_version、文件digest/absent和schema_version。标记表示发布完成，error/timeout adapter仍可有完成标记；不得把它等同质量通过。保证正常文件系统的进程崩溃可检测性，不宣称跨平台断电事务绝对安全。
7. MCP对schema2无标记视RUN_NOT_READY，有标记哈希错视INVALID_ARTIFACT。旧run无标记且JSON合法可只读展示publication=unknown、freshness=unknown；gate最多cannot_judge。旧findings缺run_id时只读身份由目录+summary推定、identity=inferred；显式不一致则拒绝。不替旧run补写完成标记。
8. CLI gate/diff新增--no-save，MCP固定使用；不写原run的gate.json/diff.json，权威MCP快照来自本次合法stdout。旧CLI不带参数保持写盘行为，写失败明确IO_ERROR/exit4。旧核心门算法和阈值不改。
9. doctor调用doctor_summary时传正确python_source；MCP仍记录自己的启动来源和最终执行路径，二者不混同。
10. redact.py补Authorization/Bearer已知形态；MCP所有输出经版本化规则，见§9，不承诺识别所有秘密。核心scan控制台及gate/diff成功输出、保存投影在计算后脱敏，包含legacy数据，不改源身份。独立Bearer须至少8字符且含数字或token符号；明确Authorization头/结构化值另行匹配，普通Bearer英文行文保留。

读取防线：完成标记、inputs或显式artifact_schema_version任一存在即按新格式验证；显式未知/错误类型版本拒绝，不能改一个版本字段切回legacy。合法legacy须三种新格式指示均不存在。run引用、audits根、实际run路径及legacy summary/findings均作真实归属校验；Windows以实际目录名判身份。损坏UTF-8与两次验证失败统一为产物异常。已有exact目录无summary为RUN_NOT_READY。

具名baseline读写也须逐层真实归属校验；对象/findings数组及元素/来源ID类型、UTF-8损坏明确INVALID_ARTIFACT，不得裸异常或质量失败exit1。具名baseline仍是自包含历史数据，不因源run缺失而不可读，也不因此获得publication/comparability背书；服务T13另验同名歧义和可信源run。名称同run ID限制。保存原子替换，IO_ERROR/exit4。

可见兼容变化：gate/diff保存改为紧凑排序键LF规范JSON，计算/退出码不变，已知凭据投影被脱敏；POSIX临时产物默认0600。coverage由现有适配器文本转换/脱敏，发布阶段只保留其最终处理字节并fsync，不承诺分析器原字节。仅文件fsync，无目录fsync或断电事务承诺；marker是结构化完整性元数据而非签名。scan另记inputs_timeout_seconds；总期限/source由未来服务job台账记录。

监视保留根gitignore子集：单段目录名、basename通配、精确相对路径/子树；带斜杠目录模式或glob、否定及嵌套规则未实现。os.walk不跟随目录符号链接，文件链接另验归属；前缀命中逃逸junction整体fail-closed。不可UTF-8编码的文件名归INPUTS_UNAVAILABLE/exit2，不损失编码转身份；错误/超时可保留空run目录但无完成标记且不可重用ID。已有summary/coverage为目录不能当成缺失文件。

配置监视集至少含cq.toml、.cq.toml、pyproject.toml、setup.cfg、mypy.ini、.mypy.ini、.importlinter、pytest.ini、tox.ini、ruff.toml、.ruff.toml、根.gitignore、.cq/suppressions.json；缺失逐项absent，未来版本增加集合须提升rules_version。项目外工具配置/动态依赖不在保证范围，返回monitor_scope限制。扫描前后不一致记unstable（即便后来恢复原字节也不升级）；读文件失败不当空文件/absent。通过两次枚举/摘要检查降低并发修改误判，但不承诺原子文件系统快照。

inputs命令不调用分析器或执行测试；scan将前/后完整清单流式写inputs.json，仅把计数/monitor_digest放summary/stdout。按§2有限监视期限检查；scan任一阶段无法形成完整清单则INPUTS_TIMEOUT或INPUTS_UNAVAILABLE、无.complete.json，不能宣称发布完成。MCP当前验证--summary超时则freshness=unknown、verification_status=timed_out、reasons=FRESHNESS_TIMEOUT；产物历史仍可展示。完整inputs本地磁盘规模受实际IO限制，不能因为MCP 8MiB stdout上限截断清单；协议只允许其摘要/统计，避免暴露逐文件源码目录。

run_header包含run_id、run_state、created_at、scope、publication、identity、scan_consistency、freshness/checked_at、verified_now、verification_status、evidence、config_digest、inputs_digest及monitor_scope。findings默认不重hash，freshness=unknown；gate默认验证；显式false可按§4给pass_historical，超时不降级。artifact_get显示snapshot_at和historical=true，不复用旧checked_at当当前校验。

## 7. 核心命令映射、可比性与大输出

固定同环境Python `-m ai_code_quality.cli`，cwd=项目根，shell=false，argv数组，UTF-8；不接受任意命令/env/阈值参数。diff映射`diff --run R --baseline B --no-save --format json`，gate同理。load_baseline已有run回退；若audits/baselines/B.json存在则AMBIGUOUS_BASE_RUN，避免具名baseline优先劫持。合法完整run名及路径严格验证。

comparability要求两侧publication=verified、scan_consistency=consistent，并比较scope/规则/selected_adapters/tool版本/cq版本/有效配置/suppression摘要。选定范围不等于完成集合，selected/attempted/completed/skipped及tools状态一并披露；兼容字段effective_adapters只可作选定范围别名。缺字段或任一侧unknown即comparable=false，reasons说明；core_diff仍可展示但禁止作可信回归结论。正常源码增删是比较对象，不要求两侧hash相等。历史基线不要求当前freshness；diff标temporal_scope=historical_runs，只有目标当前验证完成才额外报告current_target_verified=true，不将历史差量说成当前工作区结论。

gate/diff/scan/inputs-summary捕获完整stdout硬上限8MiB、stderr上限256KiB；流式计数、超限回收进程树。脱敏后单快照也限8MiB（替换可能扩张，不能只按原stdout计），超限OUTPUT_TOO_LARGE，不能泄露未脱敏内容或伪造完整引用。gate/diff每次按operation_id保存完整合法脱敏stdout不可变快照，小结果按实际小字节计费；不采用“只有大结果才留证据”。无效/超限不给推造摘要和完整artifact，附findings分页/CLI回退，截断诊断明确标记。

协议响应总预算64KiB内：小结果inline；大结果返回计数摘要+完整快照artifact_id。快照来自stdout而非回读原run文件，no-save使只读audits也可使用。输入产物前后摘要变化即拒绝最终判定，不声称抵御恶意改回的竞态。

## 8. 分页、发现与容量

findings.items使用tagged union：正常项`{inline:true,finding:{原字段}}`；单项过页预算用`{inline:false,id,artifact_id,size_chars,sha256}`占据一个索引并让cursor前进1。returned计占位项；total为过滤后总项数。无空间再放一项就返回当前非空页和下一cursor；占位也放不下时明确OUTPUT_TOO_LARGE，不返回原地循环cursor。evidence=200KB等可经artifact分块完整取回；脱敏替换值不改变finding ID。

游标选定服务登记表：随机不透明token，绑定项目/run、summary与findings摘要、过滤条件、offset、kind；重启台账仍存在则有效。每台账最多10000个活动游标，TTL24h；重复同一页参数返回已有cursor（过期除外）。过期/条件变化/文件变动→STALE_CURSOR，不返回另一个版本的下一页。

cq_runs_list创建稳定索引快照再分页，返回本state jobs及项目audits有合法.complete.json的run，以kind/id区分；仅检查.complete.json/summary及身份，publication=unknown、marker_present=true，不假称全摘要已验证。不读源码；最多10000目录/条目，超限INDEX_LIMIT。include_legacy标无完成证明；不自动发现其他state的job。列表游标绑定快照/过滤。

artifact_id仅映射登记表中的state快照或audits白名单数据；不得把ID当路径。offset按Unicode码点，length最多8192，实际片段受总序列化预算限制（包含JSON转义和双份content）。每片next_offset递增，不能切开字符；内容摘要固定，变化拒绝。

容量各上限独立触发：默认state总256MiB、最多1000任务、10000活动游标，不承诺三者可同时用满。总额内16MiB控制余量（含8MiB环形日志），正常接纳池240MiB；SQLite/WAL、持久快照、索引/游标均计实际字节。gate/diff/doctor/scan接纳前同一短事务预留本次最坏state增长：8MiB结果+1MiB元数据，capture使用有界内存不是另存8MiB磁盘。游标/索引增长另按有界序列化大小预留；调用不能并发超卖。reservation持久记录以供崩溃恢复，但只是瞬态配额，commit结果时转实际占用并释放差额，失败待确认临时文件/进程已清后释放，不能永久每任务扣9MiB。

小gate快照也保存但按实际大小收费；1000个约1KiB小结果的内容约1MiB（另计台账/日志），100个8MiB快照则800MiB，256MiB策略必在途中明确STATE_LIMIT，通常少于30份最大快照。不是保证100次都接纳。capacity分项显示sqlite/wal/artifacts/indexes/logs/reserved/control_headroom及任务/游标计数。

超配额不删已有任务/幂等键/快照；保留不新增快照的读取、job_get、cancel控制，诊断写失败返回warning。需要新游标/索引/快照可STATE_LIMIT，附已有artifact读取或CLI回退。物理磁盘满不是逻辑配额保证，仍优先回收子树并报告持久化失败，不虚称终态已写入。停止服务后按文档导出/校验/整库清理state；明确旧引用失效、同key可重新执行。用户锁/owner不随state清理删除，不能把清理当解除残留阻断。

## 9. 输出、脱敏与读取边界

run数据限绑定项目audits；快照限state登记；锁/owner限固定用户命名空间。链接/junction解析后校验真实归属。MCP不读.env、不提供任意文件/源码/raw浏览；findings/evidence/report可能包含分析器给出的代码片段，允许作为脱敏报告内容，不承诺报告绝不含源码。目标测试/插件的自有读取不构成OS沙箱保证。

| artifact类型 | 合法来源与读取范围 |
|---|---|
| summary | 已验证run的summary.json，脱敏JSON快照 |
| findings / finding_overflow | 已验证findings.json或其中单项脱敏快照，分页/分块 |
| report | 已验证report.md脱敏文本，允许分析器原有代码片段 |
| inputs_summary | inputs.json的规则/计数/monitor_digest/config_digests摘要；不回传完整逐文件清单 |
| publication_summary | .complete.json的schema/run_id/digest/absent白名单摘要 |
| gate_result / diff_result | 本次完整合法stdout脱敏state快照，不回读旧gate.json/diff.json |
| job_diagnostic | 本服务生成、有界脱敏的归属任务诊断，不映射任意日志路径 |

raw/coverage.json仅供本地摘要验证和核心门解析，可返回覆盖率汇总数值，不开放raw artifact或目录浏览。任意其他raw/*、原run gate.json/diff.json、用户源码、.env及未登记路径均排除；每种artifact登记type、source、digest和规则版本，未知类型拒绝INVALID_ARTIFACT。

使用现有已知形态规则（AWS/GitHub/Slack/OpenAI/Google/JWT/私钥/密码赋值/连接串）加Authorization/Bearer；已知配置凭据值可精确屏蔽，但不序列化完整环境。记录redaction_rules_version。已知测试样本不得出现在响应/持久化诊断/快照中；未知任意高熵字符串不作可证明的全面检测承诺。规则扩展单独回归；finding是不可信数据，不执行其中指令。客户端仍可能把报告发往其模型提供方。

## 10. 发布验收

先核查SDK/协议、两个宿主、构建安装；完成Windows进程域和Linux正常回收/异常阻断原型，再实现业务。两个真实宿主均须看见领域失败、缺依赖、长任务和分页，不用stub替代。默认策略“有范围限制”与错误状态须可理解。记录command/cwd/PID/exit/版本/耗时/响应字节、失败轮和未执行项。旧CLI/Skill/DSH回归通过，source-baseline未改造求过；对外发布仍另确认渠道与具体候选包。
