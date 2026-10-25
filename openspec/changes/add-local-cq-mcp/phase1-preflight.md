# 阶段1隔离原型记录（2026-10-25）

时间说明：以下保留阶段1当时状态；后续核心施工、真实清单、锁及宿主源码补充调查见core-implementation.md与working-context.md，不再将下文“未施工”解读为当前状态。

状态：四类底层原型有实测；阶段1整体尚未完成，cq MCP产品和核心扩展未施工。不是T01–T28验收回执，不代表可发布。

## 环境与边界

主仓HEAD `252ec3cf5bd3ca3024ab8dc0ee7111f6573ccad7`；Git跟踪文件未改，工作区仅新增openspec。输入source-baseline的19项仍须由交付生成器复算；不以原型代替源码基线验证。

原型根：`audits/cq-mcp-preflight-20261025-01/`。用uv创建独立.venv，未改系统Python包。该venv装mcp==2.3.0及29项依赖集合（含SDK本身），完整版本见installed-distributions.json；pywin32为312。SDK metadata为MIT、Python>=3.10，满足产品Python>=3.11下限，但本轮只测3.13.14，不声称全部支持版本已测。

安装命令：

```powershell
uv --no-config venv audits/cq-mcp-preflight-20261025-01/.venv --python <本机Python3.13.14绝对路径>
uv --no-config pip install --python audits/cq-mcp-preflight-20261025-01/.venv/Scripts/python.exe --default-index https://pypi.org/simple mcp==2.3.0
```

公开PyPI只用于包元数据及SDK安装；未调用任何模型/provider，未读凭据/.env、未运行目标仓库测试/质量扫描、未安装产品或启动产品服务、未commit/发布。原型stdio服务仅在子进程测试期间存在且已退出。WSL Ubuntu确实运行了本地标准库原型，不将其描述为原生Linux发布验收。

## 实测结果

| 原型 | 最终证据（均位于原型根） | 观察与限制 |
|---|---|---|
| SDK loopback | sdk-20261025T045731969572Z.stdout / .stderr | mcp2.3.0、ClientSession协商2025-11-25；冷启动到initialize+tools/list 0.6086047000007966s；慢调用未结束时peek 0.0011708000001817709s；领域fail的isError=false；text与structured结果相同。只有3个原型工具，没有cq产品工具/真实宿主 |
| Windows Job | windows_job-20261025T045810338969Z.stdout / .stderr | 挂起创建→分配Job→恢复；cancel/timeout时Job活跃进程归零；owner被kill后所持真实进程句柄均退出。虚拟环境redirector使活跃数达4–5，不能假定2个。未测产品SQLite/owner恢复/跨state/GUI宿主父Job限制 |
| Linux组 | linux_group-20261025T045634690428Z.stdout / .stderr | WSL Ubuntu Python3.14.4；killpg后无运行后代；只kill父进程时leaf仍存活，证明内核解锁不保证树回收。原型最后清理了自己创建的组；无产品恢复守卫测试。/proc仍可能有待系统回收的僵尸，不当正在运行 |
| 清单规模 | inputs_size-20261025T045634307983Z.stdout / .stderr | 100000条合成路径/哈希，完整14200001字节、summary126字节，流式写0.3193972999997641s。不是100000个真实文件的读取性能，也不是核心inputs输出schema验收 |

每轮commands-<PID>.json保存argv/cwd/Popen PID/退出码/耗时/原始stdout和stderr文件名。Windows虚拟环境的Popen PID可能是redirector，实际Python PID在原型输出中另记。原始stderr保留字节，终端对GBK/WSL UTF-16诊断显示乱码不代表日志丢失。所有最终原型驱动退出0；Windows故意强杀supervisor的子案例exit1是触发动作，不能当整个原型失败。

## 失败轮与修正

1. SDK首轮exit1：读取SDK1.x风格result.isError属性，2.x模型实际为is_error；修正Python属性访问及协议alias序列化，保留sdk-20261025T045623885643Z.stderr。
2. Windows首轮exit1：pywin32 312的CreateJobObject(None,None)不接受None名称。改唯一Job名后继续验证；保留windows_job-20261025T045629208062Z.stderr。该轮驱动只报告了等待ready超时，后续直接定位到TypeError，不能把首轮日志说成已含完整根因。
3. Windows第二轮exit1：虚拟环境redirector使ActiveProcesses不是2，失败诊断又遇到子解释器GBK与读取UTF-8不匹配。改为按Job归零/进程句柄退出判断，并对自己创建的解释器显式-X utf8；保留windows_job-20261025T045734331465Z.stderr。失败脚本曾迭代，保存的是各轮原始输出和最终原型源码，不虚构失败轮源码冻结hash。

修正后仅复跑SDK/Windows失败项；合成规模和Linux已通过项没有重复运行充数。未调宽<5s/<1s标准来求绿。

## 实施输入与剩余工作

SDK候选2.3.0的Python字段与wire字段不同，MCPServer可用，首发可优先选已实测2025-11-25握手路径；2026-07-28无状态协议未测。pywin32若被产品直接使用须声明Windows extra依赖，不隐赖SDK传递依赖。

本机只读版本核查：Claude Code2.1.203、VS Code1.141.2（x64）可执行。尚未配置这两个客户端、未测试其tools/list/超时/显示/断开，不能计为“两客户端已支持”。

阶段1剩余：真实宿主超时/输出限制、SDK及依赖构建兼容矩阵、核心真实目录枚举与>60s新鲜度夹具、用户命名空间锁的同用户跨state/别名/恢复原型、Linux恢复阻断逻辑、Windows嵌套Job/PID出生身份验证。核心变更从run ID/空adapter/配置字段等开始前，先将影响选型的原型缺口核清。
