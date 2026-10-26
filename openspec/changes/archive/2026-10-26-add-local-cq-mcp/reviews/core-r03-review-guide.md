# 核心候选 r03 复核指引

本文件供需要复核时直接使用；不是已执行审核的回执，也不要求重复整套规格审核。

请独立核对当前候选是否修复核心 r02 的明确缺口。先核包、manifest、固定 HEAD 和源码再下结论，作者报告仅作待证断言。MCP 服务未实现，不以未实现的九工具作为本批修复验收对象，也不因此免除 T10/T13 后续责任。

1. 从固定 HEAD `252ec3cf5bd3ca3024ab8dc0ee7111f6573ccad7` 重建源码，覆盖 manifest.candidates。不要直接取混有其他文件的工作区当基线；核对原字节及非候选差异。
2. 按 `core-r02-followup.md` 重验 baseline junction 的读/写、坏 JSON/UTF-8/形状、未配对代理字符文件名的 inputs/scan exit2、真实 pytest usage error、legacy gate/diff JSON/md/保存投影脱敏与 no-save。
3. coverage 必须调用真实 PytestCovAdapter 生产者再到发布边界，不能用 fake adapter 写字节证明分析器原字节承诺；当前保证已经缩为适配器处理后的字节。复验 Bearer 英文与头/结构化凭据值。
4. 检查 skipped 统计说明与核心 exit0 兼容；不得把 core_gate.passed 当 MCP verdict。评估 T10/T13 的服务责任是否足够明确，区分“本批核心缺陷未修复”与“后续服务尚未施工”。
5. 在独占临时树运行：`python -m pytest -o addopts= -q`、`python -m ruff check src tests`、`python -m ruff format --check src tests`、`python -m mypy src`。使用已有本地工具，不安装依赖、不联网、不读凭据或 .env、不改主仓/正式 .cq。
6. 独立核对 A 门仍红及来源，不把已知占位串与 MI-C 债务藏起；不用添加 suppression 换绿门。物理 32k/Linux/3.11/强杀/宿主未跑应明列，不能把历史数字改称本轮运行结果。

发现须带严重度、最小复现、命令/实际退出码/输出指针、影响及修正建议。结果文件放自己的独占路径；不要修改此候选。独立审核是否执行及使用哪个会话由用户安排。
