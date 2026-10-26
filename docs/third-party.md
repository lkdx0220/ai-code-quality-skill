# 依赖与第三方许可

cq 原创编排代码采用 [MIT](../LICENSE)。核心 CLI 的运行时依赖为空；
外部分析器由使用者另外安装，cq 通过子进程调用，不包含其源码或二进制。
分析器的许可证与上游链接见 [README](../README.md#开源工具声明与致谢必读)。

## MCP 安装依赖

可选 `mcp` extra 固定安装 `mcp==2.3.0`（MIT）；Windows 另安装 `pywin32==312`。
SDK 会引入它声明的传递依赖。这些是安装依赖，不是 cq 自研代码，也没有被复制进 cq wheel。

**pywin32 不能只按 metadata 的 `PSF` 标签理解。** 核验312版分发文件发现，
其 `win32/License.txt` 是 Mark Hammond 署名的再分发许可；还包含 Python/PSF、
Scintilla、MIT 的 MAPIStubLibrary 和 `adodbapi` 的 LGPL-2.1-or-later 等条款。
`adodbapi/adodbapi.py` 头部明确写明 LGPL 2.1 或更新版本。
cq 使用进程/Job Object 接口，不导入 adodbapi，但 pip 安装的是完整 pywin32 分发包。
应保留该上游包附带的全部许可，不能将整个环境称为“全部MIT”。

| 依赖组 | 本次样本中声明的许可证 |
|---|---|
| mcp、mcp-types、anyio、pydantic、pydantic-core 等 | MIT |
| click、httpx2、httpcore2、idna、pycparser、starlette、sse-starlette、uvicorn | BSD-3-Clause |
| cryptography | Apache-2.0 OR BSD-3-Clause |
| opentelemetry-api、python-multipart | Apache-2.0 |
| cffi 2.1.1 | MIT-0 |
| typing-extensions | PSF-2.0 |
| pywin32 312，仅Windows | 多组件许可，见上文及包内原文 |

该表是已验证安装样本的摘要，**不是所有平台和未来解析结果的完整许可清单**。
传递版本未写死在产品依赖中；每个实际候选环境应另外冻结版本、核对依赖闭包并保存许可文件。
本地发布预检记录包含各平台的版本/来源、Requires-Python、有效依赖关系、许可原文摘要与文件摘要。

## 分发边界

cq wheel/sdist 附带原创 MIT `LICENSE` 和 `NOTICE`，不附带第三方 wheel、运行环境、
审核材料、扫描结果或用户配置。正常安装由 pip/uv 获取各原始依赖分发包及其许可文件。
本候选不制作“免安装运行时合集”；若将来打包SDK、pywin32或完整环境，必须重新核对
包含的二进制、组件许可、通知和相应源码义务，不能沿用本次仅cq包的结论。
