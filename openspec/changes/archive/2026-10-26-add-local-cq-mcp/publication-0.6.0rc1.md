# 0.6.0rc1 公开发布与安装复验

日期：2026-10-26（北京时间）。状态：公开预发布成功，公开安装复验完成。
用户确认 PyPI + GitHub Releases 渠道，并在 PyPI 配置了对应 GitHub pending publisher。
不使用长期 API Token，未读取或保存用户 PyPI 凭据。

- [PyPI 0.6.0rc1](https://pypi.org/project/ai-code-quality/0.6.0rc1/)
- [GitHub 预发布](https://github.com/lkdx0220/ai-code-quality-skill/releases/tag/v0.6.0rc1)
- [Trusted Publishing 成功运行](https://github.com/lkdx0220/ai-code-quality-skill/actions/runs/40283479098)
- [发布工作流准备提交的 CI：9/9](https://github.com/lkdx0220/ai-code-quality-skill/actions/runs/40281864547)

## 发布内容与身份

版本 0.6.0rc1，不是 0.6.0 正式稳定版；GitHub 标记 prerelease，未取代旧稳定版 Latest。
tag 指向产品基线 4a3496860a163955ac4875048e49c4f1cec4a9d6。
发布工作流从 main 的 0ce4c1a 执行，仅下载 GitHub 两份冻结资产、验证大小/SHA 后通过 OIDC 上传。
没有为发布重建包，也未修改产品代码、版本、规则、阈值或豁免。

| 文件 | 字节 | SHA256 |
|---|---:|---|
| ai_code_quality-0.6.0rc1-py3-none-any.whl | 144828 | 694fcbb27f70d79bdb7fb61b96b6372fa85945b35ba46de3631a3bf656e2e084 |
| ai_code_quality-0.6.0rc1.tar.gz | 209720 | 199770884f58c781849e54877e27c187619db4e207e785c654aa51705263eb93 |

PyPI version JSON 的两份文件、摘要、未撤回状态及实际公开下载字节均与冻结包一致。
GitHub 另提供 SHA256SUMS。没有上传本地数据库、运行环境、私密配置或内部原始日志。

## 公开安装复验

使用 uv --no-config --no-cache，固定 `https://pypi.org/simple`，不使用本地包路径/离线缓存。
两平台分别创建 core-only、wheel+extra、sdist+extra 三个新环境；sdist 显式 --no-binary ai-code-quality。
未设置 PYTHONPATH，运行模块来源均为新环境 site-packages；六环境各45产品Python文件摘要与公开wheel相等。

| 环境 | 结果 |
|---|---|
| Windows/Python3.13 core-only | 仅cq distribution，UTF-8/cp936的version/help/缺extra共6项通过 |
| Linux/Python3.11 core-only | 相同6项通过 |
| Windows/Python3.13 wheel 与 sdist | 各自实际SDK stdio调用九工具、真实ruff F821、gate/diff领域失败、缺工具cannot_judge、真实pytest子树取消及回收通过 |
| Linux/Python3.11 wheel 与 sdist | 相同范围通过 |
| Windows 实际 uvx | 从PyPI无缓存解析extra，SDK stdio九工具发现、doctor/scan/poll/gate通过 |

四组安装的 JSON text 与 structuredContent 一致，isError 与调用状态相符，响应不超过64KiB。
未知键和显式null拒绝；初始化在包已安装时<5s。
uvx首次包含下载/安装的 initialize 总耗时11.831s，不能与已安装服务<5s握手混为一谈；
首次使用建议客户端 startup timeout 至少60s，实际耗时随网络变化。
这些是公开安装后的SDK验收，不冒称新一轮真实Claude/Kimi宿主验收；真实宿主记录见
[最终矩阵](final-matrix-0.6.0rc1.md)。未重跑自然大仓库性能或所有历史故障排列，因为发布字节未变。

首轮Windows脚本复制使用了错误相对路径，core包虽已从PyPI安装，但smoke脚本未找到；
保存 windows-public-first-failure.json，修正复制路径后在新runtime-r02重跑三环境通过。
这是测试启动器错误，未修改发布包，也没有将失败当通过。

## 使用与回退

```bash
python -m pip install "ai-code-quality[mcp]==0.6.0rc1"
```

客户端可直接启动独立环境中的 cq-mcp，或使用：

```bash
uvx --from "ai-code-quality[mcp]==0.6.0rc1" cq-mcp --project /absolute/trusted-project --state-dir /absolute/cq-state --tool-python /absolute/tool-python
```

分析器需要预先安装，--tool-python指向其Python；MCP不自动安装分析器。
保留旧环境和对应state。回退时先停服务并确认子树回收，再切回原command和原state；
不要删除owner文件或让旧服务接管新state。已经发布的0.6.0rc1不可覆盖；后续包内容修改必须用新版本。

## 本地证据与规格收尾

证据根：`audits/cq-mcp-publication-0.6.0rc1-20261026-01/`。
publish-run.json、github-release.json、pypi-version.json、pypi-downloads/保留公开来源；
*-public-commands.json及六组*-public-smoke/保留命令、真实响应和stderr；uvx-public-smoke/保留实际uvx记录。
verify_publication.py、verify_linux_sources.py及verification.json重新核验，verified=true。
归档ZIP只包含明确白名单，不递归纳入runtime、state或项目夹具。
现状规格同步到openspec/specs/cq-mcp/spec.md，原change以日期目录保留全部阶段与失败记录。
0.6.0正式版和其他渠道未在本轮发布。
