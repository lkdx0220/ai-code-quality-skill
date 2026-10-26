# 修复 PyPI README 并发布 0.6.0rc2

用户授权补发0.6.0rc2：rc1复用了早期冻结包，PyPI description仍声称MCP未发布。
本次只改README/公开使用文档、版本元数据、发布工作流的候选身份和发布记录；
应用逻辑、依赖、规则、阈值、测试断言、.cq保持不变。

ADDED：docs/releases/cq-mcp/0.6.0rc2.md、当前change规格/验收记录。
MODIFIED：README.md、docs/mcp.md、pyproject.toml版本及项目链接、
src/ai_code_quality/__init__.py版本字段、.github/workflows/publish-pypi.yml候选大小/摘要、
openspec/specs/cq-mcp/spec.md中的发布身份引用（行为要求不变）。
发布前核对rc1/rc2产品Python字节，除__version__外全部一致。
发布后从PyPI读取实际description并与wheel METADATA/sdist PKG-INFO/仓库README核对，
拒绝旧状态文本；公开下载、安装、CLI与SDK stdio验证通过后归档。
