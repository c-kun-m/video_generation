# B1 第一部分验收记录

日期：2026-09-08。版本：0.2.0。结论：手动内容版本、精确审批、冻结输入与可恢复模拟演练的五步实施完成。完整 B1、真实媒体生成和对外生产验收仍未完成。

## 环境与检查

Windows 11 x64；Python 3.12.6、Node 24.19.0、pnpm 11.19.0、uv 0.12.10、Docker Engine 29.2.1、PostgreSQL 17、Temporal Server 1.31.0、Temporal Python SDK 1.32.0、Electron 41.10.7。镜像和锁文件摘要见 [发布清单](../release-manifest.json)。

| 验证 | 实际结果 | 可复现入口 / 证据 |
|---|---|---|
| 后端静态与格式检查 | 通过，57 个 Python 文件 | `scripts/dev.ps1 test` |
| pytest | 54 passed，22.82 秒 | `backend/tests`；真实 PostgreSQL 与 Temporal |
| TypeScript / Prettier | 通过 | `scripts/dev.ps1 test` |
| Vitest | 30 passed | `frontend/tests`，其中 23 个共用合同样例 |
| 合同重生成 | 所有文件 SHA-256 前后一致 | `scripts/dev.ps1 contracts` |
| Windows 目录打包 | 成功 | `scripts/dev.ps1 package` |
| 打包后 Electron | 2 passed，50.4 秒 | 设置 `VIDEO_DESKTOP_EXECUTABLE` 后 `pnpm --dir frontend test:e2e` |
| 精确进程崩溃恢复 | 5 个观察点通过 | `scripts/verify_process_recovery.py --restart-temporal` |
| Alembic | 主库增量升级成功，无模型差异；隔离库升级/回退/再升级成功 | `runtime/verification/b1-migration.json` |
| 界面检查 | 实际分镜与完成页截图可读，无重叠控件 | `runtime/verification/b1-storyboard.png`、`b1-simulation-completed.png` |

Electron 测试使用打包的 `frontend/release/win-unpacked/Video Generation.exe`，验证实际 Main/Preload/Renderer 及操作系统加密存储。构建为未签名目录，需要独立后端，不是安装程序或正式发布。

## 五步验收对应

1. **内容与事务**：类型化需求/剧本/分镜、稳定段落与镜头 ID、追加版本和数据库防改写触发器；并发编辑只允许一个成功，拒绝结果也可按原命令查询。
2. **审批与冻结**：编辑和审批使用独立内容头版本；批准旧头被拒绝，新版本不继承审批；上游过期阻止新启动。批次冻结三份精确版本、审批引用及摘要。并发快照测试在两次查询之间实际提交修改，确认内容与事件游标仍来自同一时点。
3. **编排与恢复**：真实 Temporal Workflow、数据库 Outbox 租约与 Inbox 去重、独立 Worker/Dispatcher、持久化控制序号；同批次重发不另建工作流。暂停收集在途步骤后停止，恢复保留结果，取消与完成按数据库提交顺序裁决。真实历史可由 Replayer 重放。
4. **工作台**：需求、剧本和分镜编辑、历史预览、审批确认、冻结确认、批次状态和投递/消费事实；本地草稿加密并按身份与项目隔离。实际桌面进程重启恢复未保存草稿；服务器竞争更新后保留本地修改，可比较后明确采用最新保存基准。
5. **迁移与交付**：原库先备份再增量迁移；原库当时无业务记录，因此额外在恢复出的隔离库为 8 张旧表各放入一条记录，验证升级/回退/再升级后每表摘要一致。合同、已有项目功能、故障、打包、使用说明和功能证据均已核对。

## 故障证据

| 原文档矩阵 | 本轮已验证范围 | 证据 |
|---|---|---|
| E01 | 同命令 20 并发只有一个 Run、Snapshot、Outbox；不同请求复用 ID 冲突 | `test_content.py`、`test_projects.py` |
| E02 | API 在 DB 提交后、HTTP 返回前退出；查询原命令得到同一 Run | 独立进程报告 |
| E03 | Dispatcher 在发送后、确认送达前退出；租约过期重发同一 Workflow | 独立进程报告、`test_temporal.py` |
| E04 | 新内容版本必须重新审批，已冻结版本和审批记录不变 | `test_content.py`、Electron |
| E09 | 模拟步骤中取消先于完成则取消获胜；完成先提交则拒绝后续取消 | `test_simulation.py` |
| E10 | 暂停期间只收集已经开始的模拟步骤，不开始下一镜头 | `test_simulation.py`、Electron |
| E16 子集 | 项目/内容/审批/批次 API 的租户和角色隔离，以及设备会话边界 | `test_content.py`、`test_projects.py` |
| 额外恢复 | Activity 写入成功后回报前杀 Worker；重试只保留一个步骤结果 | 独立进程报告、`test_simulation.py` |
| 额外恢复 | Temporal Server 与其 PostgreSQL 保留卷重启，原运行继续完成 | 独立进程报告 |

进程报告：`evidence/reports/b1-process-recovery.json`。生产批次 `003a2c0c-4ec1-42ff-9c19-ca1e49da00ad`；Temporal run `01a07ede-14ff-7e24-8370-af47117d960c`。最终为 3 个模拟镜头结果加 1 份报告，4 个唯一 operation_id；恢复前后批次与快照身份一致。测试注入默认关闭，只有 `_test` 数据库允许开启，且须匹配具体操作 ID。

原始本机日志和截图在忽略提交的 `runtime/verification/`；脱敏结果及摘要索引在 [evidence](../evidence/README.md)。界面由 Codex 检查，不等于用户验收或真实成片质量评审。

## 明确限制

- 模拟步骤没有 LLM、ComfyUI、TTS、GPU、外部任务或媒体产物，因此不覆盖 E05–E08、E11–E15，也不能证明未知外部结果和预算处理正确。
- 当前版本固定 Workflow V1，完成过该版本历史重放；没有 Worker 滚动升级、Continue-As-New 或新旧代码兼容升级验收。
- 快照保留最近 20 个批次、最近 100 条审批；内容版本另有分页。没有长期事件清理任务、完整审片、局部重做或媒体 Range 流。
- Outbox 死信可观察并保留，尚无面向用户的死信重新投递操作。后台重启通过命令行或 IDE；没有系统服务安装或自动拉起。
- 回退迁移会删除 B1 新表，只在未写入 B1 数据的隔离库做过验证。主库升级后已有 B1 数据时应备份并前向修复，不将本次回退测试解释为无损产品降级。
- 未做公网部署、24 小时容量、真实媒体、费用、灾难恢复 RPO/RTO 或全部 G03/G04/G14 验收。功能证据中的原文档功能仍按完整范围保留 IMPLEMENTING，并单列已验证的本轮子集。
