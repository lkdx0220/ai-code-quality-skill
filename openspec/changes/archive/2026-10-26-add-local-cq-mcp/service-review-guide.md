# cq MCP 服务首批独立审核入口

目标：判断本服务候选是否可以进入跨平台/真实宿主/构建安装验收。不是要求审核者给公开发布背书。
建议仍由DeepSeek与GLM各自独立审查，彼此不看报告；本会话未替用户调用或联系这些模型。

请先自行校验ZIP全摘要、manifest成员/字节/哈希双向集合与路径安全，再阅读
candidate-tree/openspec/changes/add-local-cq-mcp/下的proposal/design/spec和service-implementation。
baseline-tree为固定HEAD 252ec3cf5bd3ca3024ab8dc0ee7111f6573ccad7的git archive，
candidate-tree为该基线覆盖本候选；不是直接把作者工作区的所有未跟踪文件抄过去。
manifest及package-verification.json描述候选变化与未改文件。自行复算，不采信作者断言。

审核重点：

1. gate verdict可信失败优先、skipped/runtime gap、历史/当前/超时、未知版本与基线可比性。
2. 并发受理/幂等、取消与完成竞态、commit后spawn前崩溃、Windows挂起加入Job和恢复。
3. OS锁≠子树已回收；Linux代码能否保守阻断，不能用Windows测试替代Linux结论。
4. 8MiB完整捕获、双份64KiB、超长finding分页推进、artifact码点分块和游标/摘要变更。
5. 状态容量结算、日志并发/IO失败、只读audits、脱敏与任意路径拒绝。
6. Popen high是否真有不受控执行入口；Windows原生字段vulture告警是否合理。
7. 构建/依赖/真实宿主尚未验收的边界是否在工具描述及docs如实披露。

复现：优先独占目录重建candidate-tree，使用已存在的可用解释器/依赖；不要修改主仓或安装依赖。
`tests/mcp/test_service.py`在Windows需mcp2.3.0+pywin32 312；缺失会skip，必须记为未验。
作者通过既有SDK隔离venv借用系统测试工具（见evidence/下verify.py），不是干净安装。
可跑 `python -m pytest tests -o addopts= -q`、ruff check/format --check、mypy src。
stdio_e2e.py的ROOT与验证解释器路径需按副本调整；记录确切命令和调整，不得偷偷改被测代码。

证据保留失败轮、两次自扫、最终gate/diff、真实SDK调用、进程测试；原生coverage不合并
服务子进程覆盖率。未附venv、缓存、SQLite状态数据库或用户锁owner；运行脚本会在副本中新建状态。
不改正式.cq，不改门阈值，不commit/push，不启服务监听远端端口，不读取.env/凭据。

请输出：结论、逐条反例及严重度、准确文件行号、执行过与没执行的项目、残余风险，
特别区分“实现缺陷”和“尚未做的平台/宿主验收”。若复测数字不同，保留完整日志和原因。
