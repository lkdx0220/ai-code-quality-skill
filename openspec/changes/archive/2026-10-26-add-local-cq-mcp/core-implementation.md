# cq MCP 核心首批实施记录（2026-10-25）

本记录仅覆盖r03核心证据扩展及补充调查，不代表cq MCP实现完成。MCP服务层尚未施工，T01–T28不得据此整组勾选；全量A门exit1，尚不可发布。主仓HEAD仍为252ec3cf5bd3ca3024ab8dc0ee7111f6573ccad7，未commit。

## 已实施

1. scan支持显式run ID，参数先验证，原子创建独占run目录；碰撞与非法ID不覆盖旧产物。CLI/API/注册表拒绝显式空adapter；None保持原默认，未知adapter保持旧exit1。
2. targets提供共享输入监视和规则版本；源/测试及13个配置路径按规范排序摘要，缺失配置逐项absent。inputs --summary不携带逐文件全集；不调用分析器。扫描前后均形成清单，记录consistent/unstable及各自checked_at；监视集合不等于分析器实际读取全集。
3. 新扫描schema2通过临时文件、flush/fsync和原子替换写入，最后发布.complete.json。摘要覆盖summary/findings/report/inputs/coverage，coverage缺失明确absent；完成标记不等于质量通过。
4. schema2加载验证发布与摘要；损坏数组、身份不符、半写和完成后coverage变化拒绝，不把损坏JSON当空finding。合法旧run保留可读，不补写marker。
5. gate/diff --no-save不写历史run；读取/保存IO失败用结构化IO_ERROR/exit4，合法质量失败仍为exit1。核心评级、差量和阈值未改。
6. Config.snapshot增加enabled_adapters/no_deepsec/respect_gitignore；解释器来源按显式选择记录，doctor传递来源。scan记录实际adapter/版本/工具期限、脱敏规则版本和输入摘要。已知脱敏规则新增Bearer，不承诺识别任意秘密。

## 实测

证据根：`C:/Users/24701/Desktop/skills开发/ai-code-quality/audits/cq-mcp-implementation-20261025-01/`。verify_core.py为每次后续命令保留argv/cwd/PID/exit/耗时及原始stdout/stderr，文件名带时间戳不覆盖；早期已有记录格式单独保留，不能虚构其缺少的字段。

| 检查 | 实测与证据 |
|---|---|
| 完整pytest | 214/214通过，0失败/0错误/0跳过；core-final.xml；33项核心证据用例包含在内，不另加计 |
| lint / format / types | core-check-final、core-format-final、core-types-final对应命令记录；ruff通过、56文件格式检查通过、mypy 31源文件无问题 |
| 核心无extra | 上述完整测试解释器未装mcp；core-facts-1792905741368478500.json记录test_interpreter_has_mcp=false |
| 最终自扫 | audits/cq-mcp-core-20261025-02，schema2完成标记实测可核验，前后输入一致；7工具ok，import-linter因未配置skipped，不能说8工具全过 |
| 覆盖率 | 2733/3321，82.29448961156278%；原始数据位于最终run/raw/coverage.json，不用显示用的82取代精度 |
| --no-save | 对最终run全部文件逐项前后SHA256相等且无新增文件；gate/diff实际退出1，完整stdout及命令见core-facts与gate-final/diff-final记录 |
| 写入失败负控 | inputs/coverage/summary/findings/report/marker六处中断均不能发布；坏marker、错身份、缺数组、读写权限错误、输入超时、扫描时源码变化均有测试 |
| 真实大清单复测 | inventory-real-r02-20261025T052302291769Z.stdout：32000/32000文件物理字节摘要正确，full/summary总摘要相等；完整9,312,754字节、摘要743字节；120s配置下两次CLI均exit0，临时夹具已清理 |

真实清单命令墙时分别为66.6483103999999s及58.902798499999335s，包含调用方读取/解析结果；不等于内部监视阶段耗时，也不能据此宣称默认60s必然超时。该实验支持保留可配置期限，不证明任意规模仓库均能按时完成。复测两个内层PID为43500/14912，argv/cwd/exit在各inventory-full/summary JSON中；未把合成清单原型当真实IO计时。

质量结果：diff新增2、修复0、仍存在0、豁免1。A门exit1，不能报绿。新增中的blocker来自既有脱敏正则误报：redact.py原37行变39行，同一source/rule/file/message，原登记仅有ID，因此失配；旧新完整finding均保留。另新增cli.py的mi-C low（7.4695450626601625），应在后续CLI边界整理中处理，不新增豁免。正式.cq未改，既有runner误报登记仍命中。核心算法不会因作者认为误报而自动豁免。

## 失败轮

- core-after.xml：212项中1项失败。作者把未知adapter退出码从1改成3，既有守卫检出；已恢复旧行为。core-after-r02.xml为212/212通过，随后补IO读取负控形成最终214项。
- 新文件初次ruff发现三处导入顺序问题，已修复；终态检查通过。首次直接ruff调用未由verify_core捕获，不能冒称具有该轮PID证据。
- 真实大清单首轮：32,000个文件，完整输出9,312,754字节、summary743字节且两者monitor_digest一致；但Windows夹具write_text产生CRLF，探针用LF预期逐文件摘要，末尾断言失败，整轮exit1，不能计通过。失败stdout/stderr保留，源码未在失败时独立冻结；首轮内层两个进程PID未持久化。复测改为写确切字节并在断言前保存每个内层命令元数据，结果另记，失败轮不覆盖。

## 补充调查

Windows/WSL跨state锁机制原型均观察到占用拒绝和释放后可重获；locking-windows/linux.json仍只证明底层机制，不能证明持久owner/出生身份/异常恢复。原型锁位置为隔离证据根，产品用户缓存命名空间尚未实现。

Claude官方文档列出每服务器timeout毫秒和MCP_TOOL_TIMEOUT；证据host-documentation.json。VS Code公共文档未列出对应配置；随后按本机1.141.2的commit 16507d91be0dc1ce4f94c04d4d0430210b8685d9获取官方源码，核对tools/call→sendRequest→JsonRpcProtocol这层未见固定调用期限。vscode-source-evidence记录URL/源码SHA/行号。不能据此保证外层调用者无期限，长调用、断开及双宿主仍须真实验收。GitHub目录API曾限流，改用公开固定commit的raw文件；未读凭据或调用模型。

## 本阶段未做

MCP九工具/协议入口；SQLite台账、配额、游标、快照；产品OS锁和进程域/恢复；MCP verdict/comparability/分页；产品wheel/sdist及双客户端安装验收；完整Windows/Linux发布矩阵；正式.cq登记重对齐；修改评级/阈值；参考DSH树修改；外部模型调用；commit/push及公开发布。
