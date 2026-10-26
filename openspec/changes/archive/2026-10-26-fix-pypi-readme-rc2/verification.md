# 0.6.0rc2 发布核验（2026-10-26）

结论：已补发公开预发布版，PyPI页面旧README问题已修复。没有发布0.6.0稳定版。

- [PyPI实际版本页面](https://pypi.org/project/ai-code-quality/0.6.0rc2/)
- [GitHub预发布](https://github.com/lkdx0220/ai-code-quality-skill/releases/tag/v0.6.0rc2)
- [发布提交CI：9/9通过](https://github.com/lkdx0220/ai-code-quality-skill/actions/runs/40290338822)
- [Trusted Publishing：成功](https://github.com/lkdx0220/ai-code-quality-skill/actions/runs/40290500613)

发布tag对应092d9915e88437706d2e88c9668e797845ed3cae。产品行为与rc1一致：
45个产品Python文件中44个与rc1 wheel原字节相同，仅__init__.py版本字符串改变。
依赖、规则、阈值、豁免和功能逻辑未改。README、元数据、版本说明及发布流程校验值更新。

## 包和页面

| 公开文件 | 字节 | SHA256 |
|---|---:|---|
| ai_code_quality-0.6.0rc2-py3-none-any.whl | 145143 | bde0b1a7c61a1779951bf022e0db208dfe5dc1d21df59ddd52c865e32e3d5dd9 |
| ai_code_quality-0.6.0rc2.tar.gz | 217447 | ddc607a2f7df1fb7f21e38282f3c2dde51b54447b22ff4960cd1a81e6304ed18 |

公开PyPI下载与冻结候选r03字节、摘要一致。wheel METADATA、sdist PKG-INFO/README、
仓库README和PyPI version JSON description正文一致（统一CRLF/LF并去除末尾换行）。
正文SHA256为65f48287b8b18e2bc22bb3edf7cae8aca051af835adf86ba9e49fe9c78e084f0。
项目元数据包含Homepage、Repository、Documentation、Issues；README文件链接包含MIT徽章均为绝对GitHub链接。

另通过隐藏IAB的真实渲染AX观察确认：标题0.6.0rc2、“本地 MCP（0.6.0rc2 公开预发布）”、
固定rc2安装命令、历史rc1验收范围说明、正确发布链接以及两份文件provenance提示。
保留的是选定AX片段记录，未声称保存完整原始AX树。

## 公开安装复验

固定https://pypi.org/simple，uv无配置、无缓存，全新venv且无PYTHONPATH。

| 平台 | core-only | wheel[mcp] | sdist[mcp] |
|---|---|---|---|
| Windows / Python 3.13 | 6项通过 | 80次调用通过 | 83次调用通过 |
| Linux / Python 3.11 | 6项通过 | 73次调用通过 | 71次调用通过 |

调用次数包含异步轮询，不作为独立用例数量。core-only验证缺MCP extra提示、版本/CLI及Windows编码兼容路径。
四个MCP环境均实际调用九工具，验证真实ruff F821、gate/diff质量失败仍是有效领域结果、缺工具cannot_judge、
真实pytest进程子树取消及cleanup=confirmed；所有采集响应不超过64KiB。
六个安装环境的45个产品文件摘要均与公开wheel一致。SDK为2.3.0，正常握手观察不超过5s。

Windows另用实际uvx无缓存从公开PyPI启动，发现九工具，doctor、ruff扫描及gate通过。
首次握手含下载安装约24.624s；这是首次运行时长，不是纯服务冷启动性能。

## 过程偏差与验收边界

1. 第一轮构建负控发现settings.py行尾被git archive归一化，严格字节比较拒绝候选。
   核对Git归一化内容后保留rc1产品原字节；最终包只改变版本字段。
2. r02本地两平台SDK验证后发现嵌套MIT徽章链接未绝对化，修文档后重建最终r03。
   r02/r03全部45个产品文件原字节相同；公开安装验证使用最终已发布r03。
3. urllib获取PyPI HTML得到HTTP200 Client Challenge，渲染断言失败并保留原响应。
   该响应不视为产品故障或页面验证通过；最终API正文、公开包验证独立通过，并由正常IAB真实页面只读核验补足渲染证据。
4. 冻结包以b71beda来源和README徽章修订构建，之后提交发布校验值。
   这里只声明产品文件、README和发行摘要一致，不声明sdist中的行政工作流文件与最终tag逐字节一致。
5. rc1完整真实宿主大结果/长调用/断开、故障和压力矩阵保持历史版本归属；本轮没有冒称全部重跑。
   rc1未覆盖、删除，GitHub保留prerelease且latest=false。

本地原始证据：audits/cq-mcp-readme-0.6.0rc2-20261026-01/。
含最终包摘要、逐文件比较、公开下载/API、浏览器观察片段、六环境命令/结果/调用记录、uvx及CI/发布工作流结果。
证据归档仅收录明确允许的脚本和日志，不含runtime、项目state、凭据或整个测试工作区。
