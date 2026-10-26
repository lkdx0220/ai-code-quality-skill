# 双模型规格审查与执行者裁定

日期：2026-10-25（Asia/Shanghai）。范围：cq MCP 的 SpecDD 文本，不涉及原神项目后续。

## 方法与证据边界

- 审阅者：`deepseek-v4-pro` 与 `glm-5.3`；模型列表接口确认可用后，分别发起独立 API 请求。
- 两者阅读同一份冻结脱敏包（四份规格 + cq 源码节选）；不提供另一模型意见。原包保存在本仓 `audits/cq-mcp-spec-review-20261025-01/packet.md`。
- 原包 SHA256：`4f0119e52dfbe43e200eecf27e6a6327f1066db7e3da9ad0d3671d5ea98e7393`。修订后的正文没有回填进旧包。
- 两者仅阅读文本，没有终端、真实客户端或项目测试能力。API 返回的 model 字段与请求型号一致；不把独立模型意见说成独立人工验收。
- GLM 普通入口因余额/资源包不可用，改走同厂商 Coding Plan；实际入口记录于本地 receipt。未使用代理，无 SDK 自动重试。
- 冻结包未包含 baseline.py/schema.py/doctor.py 的完整实现，导致部分误判；执行者在本地读取这些源码裁定，未假称模型读过它们。

## 请求轮次

| 轮次 | 实际结果 | 用途 |
|---|---|---|
| DeepSeek r01 | HTTP 200，finish_reason=length | 长报告截断，仅作补充；不能算完整审查 |
| DeepSeek r02 | HTTP 200，finish_reason=stop | 同一材料、限制输出篇幅；正式完整意见 |
| GLM r01 | HTTP 400 | 模型不支持关闭思考，失败响应保留 |
| GLM r02 | HTTP 429 / code 1113 | 普通 API 余额或资源包不可用，失败响应保留 |
| GLM r03 | HTTP 200，finish_reason=stop | Coding Plan、low 思考；正式完整意见 |

共 5 次审查 POST：2 份完整意见、1 份截断意见、2 次失败；另有 2 次 GET 模型发现。原始请求/响应/receipt 在上述 audits 目录各轮子目录，未覆盖失败记录。版本化副本 `deepseek-r02.md` 与 `glm-r03.md` 保留模型原话，不代表执行者认可其中每项。

## 正式完整意见的逐项裁定

| 来源 / ID | 模型意见 | 执行者裁定与处理 |
|---|---|---|
| GLM F-01 高 | 不能用 CLI 比较两个 run | 不成立：baseline.py::load_baseline 最后明确回退到 load_run。已在 design §6 写出真实 argv；同时补上同名具名 baseline 优先命中的真实边界，存在时返回 AMBIGUOUS_BASE_RUN，不扩写核心 |
| GLM F-02 中 | 省略 adapters 的含义未定义 | 采纳：§3 省略采用冻结默认；空/重复/越权拒绝；CLI 必传非空列表；pytest 开启权限不等于自动默认执行。T04 对应 |
| GLM F-03 中/待确认 | stored status 可能与 diff 分类混淆 | schema.py 确认扫描默认 new，登记命中 suppressed。既有枚举描述成立；§3 增加 available_statuses/classification_source，明确 new 不代表相对基线新增，避免消费误解 |
| GLM F-04 中 | 外部 shell 能改运行中服务的 env | 该触发不成立：环境由进程继承，其他 shell 改 env 不会回写已运行进程。但启动配置应显式冻结的建议合理；§2 固定子进程 env、解释器与执行配置变动策略，T21 对应 |
| GLM F-05 低 | 缺具体持锁表 | 采纳：§5 列出 doctor/scan/diff/gate 持锁，get/cancel/findings/artifact 不争执行锁。首版 doctor 保守串行，忙时明确返回，T05 对应 |
| GLM F-06 低 | 快照存储无上限 | 采纳问题、调整解法：§7 用容量/任务配额并返回 STATE_LIMIT，首版不自动删除证据或幂等键；T22 对应 |
| DeepSeek r02 F1 严重 | ok=true 与 gate 失败矛盾 | 不成立：操作成功获得有效失败结果与质量不过可以并存；原 §4 已分层。不将质量红映射成协议错误。新增 skipped 示例和消费者判定要求，T09/T10 明确区分 |
| DeepSeek r02 F2 严重 | 跨 state-dir 去重范围与 MUST 不一致 | 采纳规格精确性问题：CQ-MCP-05 与 §3 明确仅同台账去重，跨台账仅互斥；忙时不创建已接受 job；T05 对应。不引入跨台账全局任务服务 |
| DeepSeek r02 F3 高 | 核心 run_id 缺路径校验 | 原 §6 已限制字符和 containment，因此不是遗漏整个校验。补明确核心先校验单级名称，再原子创建外层目录；T06 增加 CLI 负控，不扩展成任意路径写入口 |
| DeepSeek r02 F4 高 | cancellation_requested 不在状态枚举 | 原工具表是返回字段名，未说该字段是 state 值，因此不是已证实矛盾。采纳澄清：§5 定为 bool，queued/running 维持至确认回收，并定义完成竞争和 cancel 不争锁；T07 对应 |
| DeepSeek r02 F5 中 | 游标可能只绑定 summary | 原文说文件 digest，未限定为 summary。采纳精确化：§7 明确独立绑定 findings.json SHA256 及 summary；T12 仅改 findings 的负控 |
| DeepSeek r02 F6 中 | finding 为保真可回传明文 token | 拒绝该修订建议：保留完整字段结构与 ID 不等于允许泄密。§7 明确脱敏可替换值但不截断，不重算身份；T15 同时覆盖 finding 与诊断脱敏 |

## 截断首轮中额外的有用意见

- F02/F06：原设计已经要求 gate/diff 独立快照，不是已证实原引用会被覆盖；补明确从本次 stdout 捕获、持久化到 state-dir、绝不引用原 gate.json/diff.json，T16 验证重复 A/B 调用后旧快照不变。
- F03：原设计已经禁止 loader 空数组兜底；补明确在 findings/gate/diff 入口先严格验证原始 JSON，调用前后核摘要，避免实现走捷径。
- F04：原设计已经计划原子创建；补明确独占的是外层 run 目录，而非只对 raw 子目录 exists 检查。
- F05：项目配置是受信项目的一部分，不自动升级为安全漏洞。采纳启动时显示执行配置来源并冻结；另由执行者核出 doctor 的 python_source 默认值不能直接当真实来源，写入 §2。
- F07：该项自己承认 full scope 设计自洽，且正文在句中截断，不作为完整发现。旧 run 可为 changed，T13 明确按实际 scope 判可比性。

## 当前结论

两份完整模型意见的原判定均为“有条件可实施”。执行者已核验并在正文处理本轮意见；保留 Draft / 已审查修订状态，没有声称两模型重新批准了修订稿。

本轮无须等待原项目专责，也不把双模型意见当产品接受或对外发布批准。下一步为实施前 SDK/真实客户端兼容核查，再按 tasks.md 施工与实测；用户当前要求仍处于 SpecDD 环节。

14 条需求、18 个需求场景、22 项计划验收。未执行 MCP 实现、扫描/产品测试、服务启动、依赖安装、commit 或发布。
