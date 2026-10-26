# ab3d484 测试包与真实宿主定向验收

日期：2026-10-26（UTC）；对象：`ab3d484543316a5db7577be2d31c1fe6b173d50c`。

## 结论

本批指定的大结果、长响应等待、主动取消和断开恢复场景通过，未发现需要修改产品代码的新问题。
Claude Code 2.1.203 与 Kimi Code 1.1.3 均实际调用了安装包提供的 MCP 工具。
本批不关闭完整 T19 或发布矩阵；A 门仍按上一批的 exit 1 记录，未改阈值或豁免。

## 测试包

从上述提交 `git archive` 构建，不混入工作区候选：

| 文件 | 大小 |
|---|---:|
| ai_code_quality-0.5.2-py3-none-any.whl | 141763 字节 |
| ai_code_quality-0.5.2.tar.gz | 270646 字节 |

wheel 的 MCP extra 在独立新 venv 离线安装；MCP 2.3.0、pywin32 312。
核对导入来源，并逐文件确认安装包 Python 源码与 wheel 内容一致。
运行 cwd 在独立夹具目录，移除 PYTHONPATH，使用 UTF-8。
sdist 已构建和检查成员，本批没有再次单独安装 sdist。
完整提交、摘要、成员及模块来源见证据目录 `build-result.json`。

## 夹具和方法

固定合成的已发布 base/target run；target 有 200 条 low findings，第一条使用大量中文与 emoji。
这是受控协议夹具，不冒称真实分析器检出了这些 finding。超长 finding 快照 72124 字符，
完整 diff 快照 233435 字符。另有可信 pytest 测试 sleep 45 秒，实际创建 sleep 子进程。
四个场景各有独立 project/state，真实 pytest 已启动的标记作为取消/强杀屏障。

透明 stdio 中继调用未修改的安装包入口，保留 JSON-RPC 请求、服务原响应与交付时间。
对 native 两场景的 gate 原响应延迟交付 35 秒；参数和响应正文不变。
这验证宿主在 120 秒工具期限配置下等待超过 30 秒的能力，**不是 35 秒核心运算性能测试**，
也没有覆盖 gate/diff 最坏计算期限或宿主实际超时后的所有行为。

## 结果

| 项目 | Claude Code 2.1.203 | Kimi Code 1.1.3 |
|---|---|---|
| 超长 finding 占位与两块读取 | 通过，offset 0→8192→16384 | 通过，offset 0→512→1024 |
| findings 游标翻页 | large-0/1/2 → large-3/4/5 | 同左，无重漏 |
| 大 diff | core_inline=false；200 new；快照首块可读 | 同左 |
| gate 长响应等待 | 35.327 秒，一次调用，无重试 | 35.269 秒，一次调用，无重试 |
| 主动取消 | cancelled / cleanup=confirmed / state_persisted=true | 同左 |
| 断开 | 强制终止宿主；服务取消并回收子树 | 强杀隔离服务；宿主自动重连，读到 interrupted |

两个正常会话各实际完成 11 次 cq 工具调用。Claude 会话退出 0、无权限拒绝；
Claude 模型标识来自宿主原始事件，Kimi 模型界面为 K3.1 Pro High。
Kimi 版本从本地安装程序版本信息核对为 1.1.3。
所有已交付 cq 响应的 structuredContent 与 text envelope 独立比较一致，isError=false。
这不代替两宿主的质量失败与服务调用失败映射验收。

### 断开的差异

Claude 场景：控制器只终止 Claude 宿主，不手工杀测试子树；宿主退出 1 为预期强制退出。
随后直连安装包入口重连，读到 cancelled、cleanup=confirmed、state_persisted=true。
原服务、relay、pytest 与其子进程在核验时均已退出。

Kimi 场景：先验证原服务和 pytest/子进程存活，持有进程句柄核对出生身份后，
仅终止这个隔离服务。Windows Job Object 自动回收测试子树，中继将 upstream EOF 交给宿主。
Kimi 自动重启连接，未重提 scan_start，只发 cq_job_get；实际结果为 interrupted、
cleanup=confirmed、state_persisted=true，错误说明 Previous server exited; this job is not restarted。
因此不能写成“Kimi 界面必须显示裸连接错误”；实际观察是自动重连后的明确中断结果。
之后 SDK 直连重验得到相同终态；SDK 不计作第二真实宿主。

四个 state 的预留字节最终均为 0，base/target 既有证据核验前后摘要相等。
PID 只描述核验时的身份；后续系统复用 PID 不构成旧进程残留，未向复用 PID 发信号。

## 证据及操作边界

证据根目录：`audits/cq-mcp-host-acceptance-ab3d484-20261026/`。

- packages/、build-result.json、build-commands.json：构建与安装来源。
- native/、disconnect/：Claude 命令、提示词、宿主原始 JSONL、中继、终止记录。
- kimi-native/、kimi-disconnect/：提示词、UI 文本、服务原始中继、强杀前出生身份与回收记录。
- verified-results.json：分页/分块、envelope、等待时长、恢复终态、预留与旧证据独立断言。
- config-restored.json：原有私有测试工作区配置逐字节恢复，未修改用户级配置。
- evidence-manifest.json：可复算的交付证据清单；不纳入 runtime/source 等可重建目录。

首次构建后的路径探测错误来自 cp936 输出被按 UTF-8 解码，构建与安装本身成功；
后续 UTF-8 来源和 wheel 原字节核验已修正，不把首次探测包装为成功。
核验脚本先后修正了 finding 的 inline 包装字段、SDK structured_content 属性名，
以及宿主自动重连后 JSON-RPC ID 复用的关联方式；产品代码和原始调用日志未因此修改。

Kimi 使用已信任的既有私有测试工作区，短暂切换项目级配置后恢复原字节。
用户通过物理 Escape 停止后，界面输入立即停止；不再尝试恢复原会话界面。
没有修改产品代码、正式 .cq、阈值、豁免，未 commit、push 或发布。

## 未覆盖

仍未关闭：完整九工具/缺工具/真实质量失败的双宿主全链、实际超过配置期限的长 gate/diff、
所有断开排列、宿主取消同步请求、客户端默认期限矩阵及其他发布项。
两宿主的断开方式不同，不冒称各自已覆盖宿主强杀和服务强杀的全部组合。
本次只确认指定安装包在上述明确配置和场景下的行为。
