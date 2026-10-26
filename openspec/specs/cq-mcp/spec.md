# cq MCP 现状规格（0.6.0rc1）

状态：已实现并于2026-10-26公开预发布，产品基线4a349686。
完整字段/算法契约见[归档设计](../../changes/archive/2026-10-26-add-local-cq-mcp/design.md)，
验收与公开安装范围见[发布记录](../../changes/archive/2026-10-26-add-local-cq-mcp/publication-0.6.0rc1.md)。
要求正文从已完成change同步，未改变检测规则、阈值或既有契约。

## Requirements

### Requirement: [CQ-MCP-01] 本地协议与可选依赖
MUST 使用本地stdio、规范版本协商、工具发现和调用；SDK只在可选extra，旧CLI不强制依赖。stdout仅协议；initialize不运行分析器/解释器探测或全库hash，冷启动验收<5s。
#### Scenario: 缺SDK与慢探测
GIVEN core-only安装或探测会超时，WHEN 调旧CLI/启动MCP，THEN 旧CLI可用、缺extra明确提示；extra就绪后握手不等待doctor。

### Requirement: [CQ-MCP-02] 项目、状态与执行策略
MUST绑定受信项目、state-dir及启动env/解释器策略；run读取限audits，快照限登记state，锁限固定用户命名空间/项目真实路径摘要。同用户相同命名空间跨state互斥，不承诺跨用户/直接CLI互斥。拒绝越界/设备名/链接逃逸及任意shell/env/路径。配置变化显式报错。
#### Scenario: 越界与中文路径
WHEN 输入../、绝对路径、Windows设备名或越界junction，THEN 拒绝；合法中文/空格路径以argv数组执行。

### Requirement: [CQ-MCP-03] 有限工具与副作用
MUST只提供design九工具；披露扫描写audits、状态写state、锁写用户目录。gate/diff固定--no-save，不写项目根锁。无代码修复、账本写接口、自动安装或commit。
#### Scenario: 只读扫描产物
GIVEN 项目根及audits只读、state/用户锁可写，WHEN gate/diff，THEN 仍返回结果且不写项目。

### Requirement: [CQ-MCP-04] 显式扫描策略
MUST将省略adapters解析为ruff-check/ruff-format/mypy/radon/vulture五项，import-linter/deepsec需显式选择；未选维度披露为out_of_scope。显式空/重复/越权拒绝；核心API/CLI/注册表也拒绝显式空，仅None保留旧默认。pytest需启动允许且本次显式选择。
#### Scenario: 空参数与测试权限
WHEN --adapters空串、API空数组或未授权pytest，THEN 在执行分析器前失败，不能回退全量。

### Requirement: [CQ-MCP-05] 事务幂等与互斥
MUST以SQLite短事务原子完成同台账查重/容量预留/执行锁/接受任务；相同key同参包括终态均复用，异参冲突。预留在完成/安全失败后转实际占用并释放差额，忙时不创建已接受job。同OS用户/固定锁命名空间跨台账互斥。
#### Scenario: 并发与终态重试
WHEN 同台账两个同key请求同时到达或取消后重试，THEN 返回同job；终态附reused/terminal_state和换key重跑提示。

### Requirement: [CQ-MCP-06] run独占与完成发布
MUST受理扫描时预生成mcp-UUID并返回，未建目录标pending，不当已发布结果。核心校验ID、原子建目录、拒绝碰撞；全部证据完成才发布.complete.json摘要。标记只证明文件发布完成，不证明质量通过。
#### Scenario: 半写与撞目录
WHEN 写summary后被终止，THEN 无完成标记、不可当已发布；预置目录遇碰撞不改旧字节。

### Requirement: [CQ-MCP-07] 可取消任务与平台边界
MUST doctor/scan异步提交、有有限总期限；cancel/get受理不被扫描阻塞。确认归属子树回收后才终态和释放执行权。OS锁释放不等于残留树已清；无法确认需阻断。Linux异常强杀不保证自动回收，必须明示并验证恢复阻断。
#### Scenario: 取消窗口与异常退出
WHEN cancel落在queued/spawn间或宿主强杀，THEN 启动前复查、终态不虚报，重启核查残留；不误杀重用PID。

### Requirement: [CQ-MCP-08] 领域结果与证据判定
MUST区分调用成功、原exit、声明范围、scan_consistency、freshness/verified_now及temporal_scope。gate/diff exit1为有效结果；gate/diff3与IO/损坏为调用错误。verdict按design算法；显式不验证可pass_historical并保留scope_gaps，但未知/过期不允许无条件pass，验证超时不能静默历史通过。
#### Scenario: 默认范围与过期
WHEN 默认五项正常且无质量失败，未装DeepSec/未配import-linter、无pytest/baseline而当前验证一致，THEN pass_with_gaps并点名排除；显式DeepSec却缺失则cannot_judge；verify_current=false只可pass_historical；验证超时cannot_judge附FRESHNESS_TIMEOUT；原core_gate保留。

### Requirement: [CQ-MCP-09] 分页与超限
MUST验证JSON/身份/文件摘要；游标用持久化登记绑定内容。超长finding返回带artifact的占位项并前进；超capture硬限报错、不得从截断JSON推造摘要。响应总预算计双份内容与转义。
#### Scenario: 单项和整结果超限
WHEN 单项200KB或diff大于8MiB，THEN 前者占位+完整分块、游标推进，后者OUTPUT_TOO_LARGE附可操作回退。

### Requirement: [CQ-MCP-10] 差量可比性
MUST复用核心gate/diff，配置快照补全有效adapter/ignore/no_deepsec等字段，比较scope/规则/工具版本/配置/suppression。任一侧publication非verified或scan_consistency非consistent即comparable=false；未知字段不默认相同，正常源码变化不单独导致不可比。
#### Scenario: ignore策略变化
WHEN 仅respect_gitignore不同，THEN comparable=false并点名；普通源码修复允许在同策略下比较。

### Requirement: [CQ-MCP-11] 单一输入清单与读取头
MUST由核心targets共享枚举生成清单、前后hash和cq inputs；MCP固定inputs --summary避免大清单stdout，不得复制walk规则。输入规则v2先脱敏展示路径，以path_sha256区分原始路径身份，再计算可复算monitor_digest；摘要包含脱敏规则版本。期限默认60s、启动可调1..600；扫描清单不完整不发布标记。此为监视集合而非实际读取全集；所有读结果带run_header，未本次验证freshness=unknown。
#### Scenario: 新增、删除与旧run
WHEN 修改/新增/删除py后显式verify_current，THEN stale；旧run无标记合法时publication/freshness=unknown，缺失run_id只允许明确推定身份展示。

### Requirement: [CQ-MCP-12] 有界脱敏与产物读取
MUST按版本化已知规则脱敏，含Authorization/Bearer；不承诺未知秘密必检出。artifact严格按design类型白名单；报告可含分析器原有代码片段，但不提供任意源码/.env/raw读取。coverage仅本地解析摘要，inputs仅汇总；目标测试自有读取不是沙箱保证。
#### Scenario: 已知凭据
WHEN finding/异常含已知测试token，THEN 输出与诊断均替换，finding ID保留；未知形态限制须披露。

### Requirement: [CQ-MCP-13] 兼容与真实安装
MUST从wheel/sdist验证核心和extra安装，记录SDK/Python/OS/协议版本及两个真实宿主。旧正常CLI语义保留，run碰撞/显式空adapter行为修正明确记录。
#### Scenario: 独立宿主
WHEN 两宿主连接构建包，THEN 能完成doctor job、扫描、查询、历史发现、分页和gate/diff；缺项如实显示。

### Requirement: [CQ-MCP-14] 发布证据
MUST保留失败轮、原始输出、命令与验收范围；静态审查不当运行通过。必验未执行不得标发布完成，平台异常边界公开。
#### Scenario: 未执行场景
WHEN 第二宿主或Windows回收未测，THEN 保持候选/未完成，不以skip顶替。

### Requirement: [CQ-MCP-15] 历史发现与容量
MUST提供只读分页runs/job索引，跨客户端发现同项目已发布run，旧/外部身份限制明确。256MiB/1000任务/10000游标是独立上限，不保证同时用满；同事务瞬态预留，按实际快照字节结算，不并发超卖；满时拒新增，保留既有读/取消控制和证据。
#### Scenario: 跨会话与容量满
WHEN 客户端无run_id记忆或state配额满，THEN 可列已有run并分页读取；新任务STATE_LIMIT，不删除幂等键后偷偷重跑。
# 控制通道故障补充场景（2026-10-26）

### Scenario: 工具解释器保留虚拟环境身份
- GIVEN CLI参数、CQ_PYTHON、项目配置或默认解释器指向POSIX虚拟环境的Python符号链接
- WHEN启动服务冻结工具解释器
- THEN固定绝对路径但不得解引用该可执行文件符号链接，实际执行仍能导入该venv独有的工具。
- AND启动仍不探测或安装工具；项目/state真实归属校验不受此解释器规则影响。

以下场景补充已有取消/期限/容量要求，不替换原验收矩阵。

### Scenario: SQLite写锁不阻塞查询和错误审计
- GIVEN独立进程持有state数据库写锁
- WHEN查询已存在job，或提交类型错误的job_get
- THEN只读查询成功，参数错误仍返回INVALID_ARGUMENT；受理返回各<1s，审计不再依赖数据库写锁。
- AND独占锁使读取不能成功时，在控制预算内返回STATE_BUSY，不串行再等待5s审计。

### Scenario: 本owner满盘取消与终态补记
- GIVEN本服务运行的子树且state物理空间为0
- WHEN调用job_cancel
- THEN先发内存取消信号，<1s返回接纳；标记无法落盘时明确cancellation_persisted=false及warning。
- AND子树回收确认后job_get可显示内存终态、cleanup=confirmed、state_persisted=false，不能只显示旧running。
- WHEN释放空间并再次job_get或发起新执行
- THEN终态及预留原子补记，旧证据不变；已完成任务不因迟到取消而重写。

### Scenario: 跨实例与期限故障边界
- GIVEN不同服务实例使用同state，取消标记可写时通过轮询送达；不可写时返回结构化失败
- THEN不把另一实例任务伪称为本地信号接纳，不按外部PID直接回收。
- AND独立数据库写锁/读锁竞争期间，执行循环的期限不被5s数据库轮询阻断。
- AND服务在pending终态尚未落盘时崩溃，重启仍先核对进程域，再保守标interrupted，不重放任务。

### Scenario: 启动转换遇瞬时写锁
- GIVEN已受理且持项目执行权的queued任务，queued→running被独立写锁阻挡
- THEN仅STATE_BUSY有限重试2s且受总期限限制，持久化running成功前不得spawn。
- AND get/cancel不等待这段重试；取消或期限先到则无spawn并记录对应终态，IO_ERROR不重试。
- AND启动等待计入执行预算，重试不额外延长总期限；持续锁竞争明确failed/STATE_BUSY。

### Scenario: 二次存储错误不替换主错误
- WHEN事务主操作失败且rollback/close又发生SQLite错误
- THEN保留主业务错误或STATE_BUSY/IO_ERROR映射，不让二次OperationalError逃逸；进程中断仍可传播。
- AND主操作成功但close失败时明确IO_ERROR，不假称成功。

### Scenario: 已提交pending快照无需再次读取
- WHEN job_get已成功补记pending终态及预留，但随后的存储读取不可用
- THEN直接返回已提交快照的state_persisted=true，不把已确认提交误报为内存未落盘。

### Scenario: gate/diff崩溃后的预留回收
- GIVEN gate/diff已提交op-*预留，服务owner在finally前退出
- WHEN下一次gate/diff或新key doctor/scan在同state接纳执行
- THEN先持有同项目执行锁并确认旧进程域安全，再与新接纳同事务清理旧op-*并检查容量。
- AND进程仍活动、残留树未清、owner意图损坏或锁仍被占用时不回收，不按年龄/PID消失判空闲。
- AND仅清理本state无关联job的op-*；job预留/幂等键、已存artifact、cursor和其他state保持不变。
- AND恢复事务失败整体回滚，重试可恢复；崩溃操作不重放、不伪造成功或空结果。
- AND同key重用和查询不抢执行锁做清理；其他state的操作不隐式打开旧state，旧state下次执行再回收。

### Scenario: 核心子命令仅接纳参数数组
- GIVEN执行入口接收内部构造的核心子命令
- THEN仅接纳非空list/tuple，元素均为不含NUL的字符串且可执行文件项非空；在写入执行意图前拒绝其他形状。
- AND复制参数序列后执行，POSIX显式shell=False；空参数、空格、引号、中文和shell特殊字符作为独立参数原样传递。
- AND保留原有Job Object/进程组、取消、期限和残留回收语义，不开放调用方任意命令工具。
