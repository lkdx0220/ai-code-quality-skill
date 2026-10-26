# MCP CI 接线修订（2026-10-26）

## 失败与根因

GitHub Actions `40269121430`（da0b648）和前一轮 `40268730819` 未通过。
前者 Ubuntu/Python 3.11 的 test 和 Ubuntu dogfood 均有19个 SDK 导入失败：
`ImportError: cannot import name 'ClientSession' from 'mcp' (unknown location)`。
其他矩阵被 fail-fast 取消，不能计作通过。

旧 workflow 只安装核心包，没有安装 MCP extra。pytest 将 tests 加入导入路径后，
`tests/mcp/` 可以被识别为名为 mcp 的 namespace package，因而
`pytest.importorskip("mcp")` 并不证明 SDK 已安装。

## 修订

- test 矩阵保留 Ubuntu/Python 3.11 核心无依赖安装，并检查 MCP distribution 确实不存在。
- Ubuntu/Python 3.11、3.13 和 Windows/Python 3.13 安装声明的 MCP extra，执行 SDK 导入预检及原完整测试集。
- 两平台 dogfood 安装同一 MCP extra，避免自扫里的 pytest 再遇缺 SDK。
- SDK 依赖测试检查具体模块 `mcp.client.session`，避免被同名 namespace 误导。
- test/dogfood 关闭 fail-fast，单平台失败不取消其他平台的证据采集。

不修改产品逻辑、依赖版本、检测规则、阈值或豁免。

## 本地验证

| 环境 | 通过 | 跳过 | 失败/错误 |
|---|---:|---:|---:|
| Windows/Python 3.13，系统解释器无 MCP SDK | 351 | 113 | 0 |
| Windows/Python 3.13，MCP 2.3.0/pywin32 312 runtime | 452 | 12 | 0 |
| WSL Ubuntu/Python 3.11，MCP SDK runtime | 454 | 10 | 0 |

计数来自 JUnit，三组均采集464项。无 SDK 环境的跳过还包括缺少 Windows 可选依赖的进程测试，
不能把351项通过称为完整 MCP 验收。两组带 SDK 的默认跳过包括容量/实际满盘显式开关及平台专用项，
本轮未重跑这些独立验收。Windows runtime 通过 PYTHONPATH 使用源码及既有系统分析器库；
Linux 使用源码 PYTHONPATH。本轮不是新包安装验收。

ruff check、ruff format（87文件）、mypy（45源码文件）、workflow YAML矩阵解析和
git diff --check 均通过。证据在 `audits/cq-mcp-ci-fix-20261026-01/`：
先前远端失败日志、三组原始日志及JUnit。远端结论须以修订提交触发的 Actions 为准。
本轮不据此关闭完整宿主或正式发布矩阵。
