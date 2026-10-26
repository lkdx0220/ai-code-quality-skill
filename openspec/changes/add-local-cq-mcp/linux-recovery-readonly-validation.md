# Linux 恢复阻断及只读项目验收

日期：2026-10-26。基线 HEAD `32849e114c9ae7ee96bf86e2a6b90c86f7a95ebc`。
本轮新增测试与验收记录，未改产品代码、正式 `.cq`、阈值、用户宿主配置或发布状态。

## 强杀恢复：4/4 通过

新增 `tests/mcp/test_posix_recovery.py` 及 `fixtures/posix_owner.py`。
WSL Ubuntu / CPython 3.11.16 运行真实 Service/SQLite/OS 锁/进程组实现；将 doctor 的
受控子命令替换为可观测的睡眠进程树，以稳定注入崩溃时机。不是完整 stdio 宿主强杀验收。

四种组合：提交事务完成但尚未 spawn、运行中已有两级进程树，分别使用同 state 和另一
state 的竞争服务。真实 SIGKILL 后确认 owner exit=-9。

- 运行中 owner 死亡后，子进程和后代确实仍活着；doctor/scan 新提交以及旧 job_get
  均返回 CLEANUP_FAILED，未修改旧 owner 记录、未虚构 completed，也没有接受新 job。
- 列表查询仍可用。测试仅在出生身份匹配后终止自身夹具进程组；确认组内无运行成员后，
  原 job_get 恢复为 interrupted / cleanup=confirmed，无结果、无退出码。
- 同 key 返回原 interrupted job，不重跑；预留释放；新 key 可受理，随后取消并关闭服务。
- 提交后尚未 spawn 的窗口同样恢复 interrupted，不启动历史任务。

命令：在已有 `/root/cq-mcp-linux-tests-20261025-01/bin/python` 环境，以源码 PYTHONPATH
执行 `pytest tests/mcp/test_posix_recovery.py -vv -s`。最终 4 passed / 3.06s。
首轮 4 failed：夹具把已冻结环境重复传给子服务，导致 PYTHONPATH 重复、幂等摘要改变。
修正为传启动环境后复跑成功，未改产品幂等规则。首轮 JUnit 保留。

## 只读项目：真实普通 UID 通过

隔离 Linux 文件系统夹具先创建 Git 仓库和两次真实 ruff-check 扫描，随后将整个项目
目录设为 0555、文件设为 0444。reader 使用 UID/GID 65534、清空附加组、独立可写
HOME/state；三次负控确认项目根、audits 以及已有 summary 均不能写入。

reader 使用系统 Python 3.14.4，setup 为 Python 3.11.16，ruff 扫描使用已有 Linux
venv。该权限探针不等于干净安装或完整 Python 3.14 兼容性验收。

- 历史 gate 为 pass_historical；请求当前验证的 gate 为 pass_with_gaps。
- diff 成功且两侧 comparable；三份 state 快照均可经 artifact_get 读取。
- 项目 41 个文件的 SHA256 和权限模式完全不变，无新增文件，Git 状态前后均为空。
- 未新增项目根锁；旧 CLI gate/diff 默认写盘分别返回 exit4 / IO_ERROR。

证据脚本 `audits/cq-mcp-host-20261025-01/readonly_probe.py`，最终 reader 耗时约 2.38s。
首轮服务调用成功，但检查失败：root 侧探针自己的 git status 刷新 .git/index。
改用 git --no-optional-locks 后复跑通过；原始失败 JSON 保留，没有排除 .git 来规避比较。

## 证据与剩余边界

`audits/cq-mcp-host-20261025-01/` 保存：

- linux-recovery-r01-junit.xml、linux-recovery-r02-junit.xml、linux-recovery-r02.stdout。
- linux-readonly-r01.json、linux-readonly-r02.json（全部响应、argv、退出码、文件清单）。
- linux-acceptance-manifest-20261026.json（脚本/测试/日志的大小与摘要）。

新增测试 lint/format 检查通过。未重新跑无关完整回归；产品未改。
本轮关闭 T08 Linux 残留阻断场景、T26 提交后/spawn 后两个窗口及 T16 Linux 只读子集，
不关闭完整 T08/T16/T26。未验提交前、creating 意图窗口、spawn 与持久化竞态、真实
stdio 宿主 SIGKILL、PID 重用、Windows 只读 ACL、磁盘满与全部容量/崩溃矩阵。
