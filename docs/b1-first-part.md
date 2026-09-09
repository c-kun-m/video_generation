# B1 第一部分：内容版本与可恢复演练

范围是手动编辑、不可变内容版本、审批、冻结输入、PostgreSQL Outbox/Inbox 和真实 Temporal 上的模拟制作。没有真实 Agent、ComfyUI、配音、预算、GPU 调度或视频文件。本轮不是完整 B1 验收。

## 运行

在项目根目录 PowerShell 中运行：

```powershell
./scripts/dev.ps1 setup
./scripts/dev.ps1 start
```

`start` 按根目录 `startup.yml` 的开关准备基础服务并启动各进程，详见 [YAML 统一启动](startup-yaml.md)。另开终端运行 `./scripts/dev.ps1 pair` 生成一次性配对码。已配对设备继续使用原身份。关闭桌面不会停止 API、投递器、Worker 或数据库；在启动终端 Ctrl+C 会停止本次管理的应用进程，Docker 服务保留。

PyCharm 只打开 `backend` 时仍选择 `.venv` 解释器，并将 `src` 标为 Sources Root；共享运行配置新增 `Video Temporal Worker`、`Video Outbox Dispatcher`、`Video Initialize Temporal`。对应 CLI 是 `python -m video_generation worker`、`dispatcher`、`init-temporal`。

业务数据库保留原有命名卷。Temporal 使用独立 PostgreSQL 服务和 `video-generation_temporal-postgres-data` 命名卷、独立密码；仅 Temporal 的 7233 端口暴露在回环地址。Temporal 1.31.0、Python SDK 1.32.0 已通过本机集成测试，镜像与依赖由 Compose / uv.lock 固定。

`infra` 会初始化/校验 Temporal schema 并创建 `video-development` namespace，保留已存在数据；不可通过删除卷解决密码、迁移或恢复问题。Temporal schema 初始化与业务 Alembic 迁移是两个不同步骤。

如果 Docker daemon 的镜像源无法访问官方镜像，但 Windows 主机代理可以访问 Docker Hub，可使用仓库提供的官方镜像导入工具：

```powershell
python scripts/pull_official_image.py temporalio/server 1.31.0
python scripts/pull_official_image.py temporalio/admin-tools 1.31.0
./scripts/dev.ps1 infra
```

该工具只从官方 Docker Hub 读取允许的仓库，验证 manifest 与每层 SHA-256，通过 OCI archive 导入 Docker 的 containerd image store，不修改全局 Docker 配置。缓存保存在忽略提交的 `runtime/image-cache`。当前 Compose 固定 linux/amd64；此方式服务于本轮 Windows x64 本机环境。

## 使用流程

1. 打开项目的需求页，填写主题、受众、目的、风格；可以先填充示例。点击保存新版本，再批准当前版本。
2. 在剧本页关联当前需求，编辑带稳定标识的旁白段落及画面描述，保存并批准。
3. 在分镜页关联当前剧本，填写 3–8 个镜头、运镜、计划时长及旁白关联。24 fps 下总时长须为 30–60 秒，且覆盖所有剧本段落；这些时长不是实际 TTS 测量值。
4. 在模拟演练页检查要冻结的内容，确认启动。每个镜头默认模拟 5 秒，然后保存演练报告，不生成媒体文件。
5. 暂停允许当前模拟步骤结束，再停在安全位置；恢复复用快照和已保存步骤。取消被保存后不能再恢复，最终状态以后台确认停止为准。

只有 owner/editor 可以编辑、启动或控制；owner/reviewer 可以审批。已有审批不传播到新版本。撤销审批会阻止依赖它的新启动，已经启动的批次仍需单独取消。项目归档后不能编辑或新启动，已有批次仍允许控制。

编辑器通过 Main 进程加密保存本地未提交草稿，按 tenant/actor/project/content-kind 隔离。配对凭据和草稿不会直接进入网页存储。版本冲突不会覆盖草稿；先查看服务器最新版本，再明确选择是否以最新版本为基础保留修改。

## 持久化与接口

`application` 协调命令、权限和事务；`domain` 放身份与内容规则；SQLAlchemy 模型和连接配置在 `infrastructure/persistence`。Temporal Workflow 在 `orchestration`，只编排确定性消息/定时器；数据库访问在 Activity 调用的应用服务中。独立进程入口放在 `workers`。

内容保存追加 `content_revisions`，移动 `content_heads`；审批追加 `approvals`。版本、审批、冻结快照和步骤结果有数据库防改写触发器。当前头的 `row_version` 包括保存和审批变化，独立于项目元数据的版本。

所有写操作使用 `(tenant_id, actor_id, command_id)` 与规范请求摘要去重。创建批次与快照、命令记录、项目事件及 Outbox 同事务提交。HTTP 202 / ACCEPTED 表示命令已持久化；APPLIED 表示后台已经处理该命令，制作是否结束看批次状态。

Outbox 租约为 30 秒，失败指数退避至最大 60 秒，24 小时后保留为 DEAD。SENT 仅代表传输送达；Inbox 与消费者状态修改同事务提交。投递器会重新通知缺少消费记录的有效批次，并检查业务状态与 Temporal 是否一致。

新增业务接口前缀均为 `/video/v1`：

- `POST /projects/{id}/revisions`、`GET /projects/{id}/revisions?entity_kind=brief|script|storyboard`。
- `POST /projects/{id}/approvals`、`GET /projects/{id}/approvals?revision_id=...`。
- `POST /projects/{id}/production-runs`，仅接受 `execution_mode: simulation`。
- `GET /production-runs/{id}`、`POST /production-runs/{id}/commands`（pause/resume/cancel）。
- `GET /system/execution-status`：工作进程最近心跳及本租户未投递、死信计数。
- 现有命令查询、项目快照及事件接口同时支持新业务类型。

项目快照和批次详情采用一致性读取事务；项目事件仍按提交顺序分配游标，桌面断线通过游标或重新读取快照恢复。历史版本按 revision 分页；快照只带当前内容、最近审批与最近批次，历史内容按需查询。

## 验证与边界

`./scripts/dev.ps1 test` 需要业务 PostgreSQL 和 Temporal 已启动。普通测试使用独立测试库，Temporal 集成测试使用 `video-tests` namespace 和随机队列，不调用真实模型。`test-e2e` 使用独立桌面配置与测试进程，只有自己启动的进程会被停止。

五步实施已完成，详见 [分步进度](b1-progress.md) 和 [v0.2.0 验收记录](b1-verification.md)。后端 54 项、前端 30 项、打包后桌面端到端 2 项通过，并有独立真实进程崩溃恢复报告。发布摘要固定在根目录 `release-manifest.json`。

当前不提供 Temporal Worker 滚动版本升级、Continue-As-New、真实外部任务未知结果处置或公网部署。这些仍属于后续开发。
