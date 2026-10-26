## ADDED Requirements

### Requirement: 发布描述与包内容一致
公开版本的PyPI description MUST等于验收的发行包README，版本安装命令MUST与该版本一致。
README内的本仓库文件链接MUST能从PyPI访问，不依赖PyPI相对路径解析。

#### Scenario: 文档修订发布
GIVEN rc1已发布且不能覆盖，WHEN用户授权发布仅含文档和版本修订的rc2，
THEN新包版本、__version__、README安装命令一致，应用逻辑字节保持不变；
PyPI实际version JSON中的description等于wheel和sdist中说明正文，不再宣称MCP尚未发布。
