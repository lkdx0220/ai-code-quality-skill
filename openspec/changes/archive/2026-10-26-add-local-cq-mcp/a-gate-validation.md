# A 门收尾验证

日期：2026-10-26。基线提交 ab3d484，本批为其上的未提交源码修订。

## 结论

自扫 `cq-mcp-a-gate-selfscan-20261026-01` 的 A 门 exit 0、passed=true。
相对冻结基线：新增0、消除告警2、仍存在5、豁免1；blocker/high均为0。
覆盖率4047/4811=84.1197%，原阈值80%；无D/E/F圈复杂度。
这关闭原先A门两项阻断，不代表没有低危提示或完整发布矩阵已关闭。

## 原因与处理

1. redact.py 注释中的占位数据库连接串被DeepSec密钥正则当成真实口令；
   改为自然语言说明，不改变脱敏正则或规则版本，也不删除实际连接串脱敏能力。
2. POSIX进程入口接收内部生成的argv数组且未启用shell，但DeepSec的局部AST分析
   不追踪变量类型，将函数参数argv误标成命令注入。明确非空list/tuple和字符串/NUL校验，
   在写执行意图前拒绝畸形输入；冻结为tuple，Popen接收复制后的列表并显式shell=False。
   Windows继续按同一校验后的数组生成命令行；Job Object/进程组与清理逻辑不变。

两项原告警均非已证实的安全漏洞。本批是移除假凭据示例和加强进程参数契约，
没有将Popen换成间接调用规避检测，没有改DeepSec源码、严重度、质量门算法/阈值，
没有新增、迁移或重写suppression；.cq文件摘要与修前一致。

同一未改动DeepSec规则的before/after探针：两项告警均能在修前源码复现，修后不再出现；
动态shell=True正向对照及带口令数据库连接串正向对照仍能检出。
探针只把安全合成内容放在内存，不执行其命令。

## 验证

| 范围 | 结果 |
|---|---|
| 新增参数边界测试 | Windows12通过；拒绝命令字符串/bytes/空数组/非字符串/NUL；list与tuple实际启动Python，空串、中文emoji、引号、换行及shell元字符原样传递，无注入文件 |
| Windows完整自扫 | 452通过、12跳过、无失败；pytest工具ok；自扫145.276秒 |
| Linux受影响进程/服务/崩溃恢复 | 87通过、1跳过、无失败/error；含新增12项、真实stdio/owner强杀及残留阻断；整轮65.703秒 |
| 静态 | ruff/check、ruff/format、mypy、git diff --check均exit0 |
| 核心diff与A门 | 均exit0，scan_consistency=consistent |

Windows12跳过为默认关闭的6个容量压力、4个Linux/POSIX、2个真实满盘场景，不计通过；
本批未重跑容量或真实满盘，既有对应证据仍按历史记录。
Linux唯一跳过为Windows专用Job Object owner-death测试，此路径在Windows自扫实际执行。
Windows自扫沿用pytest的双quiet配置，没有数字汇总行；计数独立解析实际进度行得到464项
（452个通过符号、12个跳过符号），未从采集数推定通过；Linux计数来自JUnit。

7工具ok，import-linter因本仓无架构契约配置skipped，不能将此项写成通过。
核心A门的全部已有检查通过，但不据此假称MCP对“显式选择却skipped”的范围给出无条件pass；
现有MCP verdict策略保持不变。

仍有5条low提示：cli.py可维护性指数C，以及pywin32原生结构的4个动态属性被vulture标未读。
原有runner.py命令调用误报登记仍为suppressed；陈旧的注释示例旧登记未删除。
本批没有为消除这些提示扩大重构或豁免范围。

## 证据与范围

- `audits/cq-mcp-a-gate-20261026-01/`：修前字节摘要/源码、doctor、冻结基线、命令与原始stdout/stderr、JUnit、规则探针、verified-results.json、交付清单。
- `audits/cq-mcp-a-gate-selfscan-20261026-01/`：发布marker、summary/findings/inputs/report及分析器原始产物和coverage。
- 具名冻结基线：`cq-mcp-a-gate-before-20261026-01`，来源为前一批op-recovery自扫。

首次格式检查指出2文件需格式化，按ruff默认格式修正后复验通过；未更改断言或工具配置。
检测能力由底层ruff/mypy/radon/vulture/pytest/import-linter/DeepSec提供，cq负责聚合编排；
这里的A为本地quality gate近似口径，非Sonar官方评级。

先前真实宿主证据仍绑定ab3d484构建包；本批验证的是修订源码，不把旧安装包冒称新候选包。
本批未重新安装依赖、构建发布包、commit、push或发布。完整发布矩阵仍以tasks为准。
