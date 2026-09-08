# 开发与运行

只在 PyCharm 打开 `backend` 时，使用 [后端 IDE 配置说明](../backend/README.md) 和共享 `.run` 配置。

## 环境与配置

在仓库根目录运行 `scripts/dev.ps1`。推荐 PowerShell 7，Windows PowerShell 5.1 也可运行脚本。使用 Python 3.12、Node 24、pnpm 11.19.0；`python -m uv` 避免 uv 用户安装目录不在 PATH 的问题。Docker Desktop 需要先启动 Linux 容器引擎。

`setup` 在缺少 `.env` 时生成业务配置；升级时补充缺失的独立 Temporal 数据库密码，不覆盖已有有效密码。业务数据库使用 `video-generation_postgres-data` 命名卷，Temporal 使用独立 PostgreSQL 服务与 `video-generation_temporal-postgres-data` 命名卷。暴露端口仅绑定回环地址。

| 命令 | 用途 |
|---|---|
| `check` | 检查 Python、Node、pnpm、uv 和 Docker 服务 |
| `setup` | 创建本机配置，按锁文件安装依赖 |
| `infra` | 启动业务数据库、Temporal 及其独立数据库，并初始化 namespace |
| `dispatcher` / `worker` | 分别启动独立 Outbox 投递器和 Temporal Worker |
| `init-temporal` | 幂等创建当前 Temporal namespace |
| `migrate` | 执行 Alembic 迁移 |
| `pair` | 初始化本机 owner，生成或更新一次性配对码 |
| `backend` | 前台启动 API；Ctrl+C 停止此进程 |
| `desktop` | 启动 Electron 与 React HMR |
| `contracts` | Pydantic → JSON Schema / OpenAPI → TypeScript |
| `test` | Ruff、Python/数据库测试、TypeScript 检查和 Vitest |
| `test-e2e` | 构建并运行真实 Electron 桌面验证 |
| `build` / `preview` | 构建 / 运行生产前端资源 |
| `package` | 生成 Windows 目录构建 |

API 默认 `127.0.0.1:8000`。若变更端口，同时修改 `.env` 的 `VIDEO_API_PORT` 和 `VIDEO_SERVICE_URL`。此版本不支持远程服务地址。Swagger 文档位于本机 `/docs`；业务接口仍需设备 session。健康检查为 `/health/live` 与 `/health/ready`，后者验证数据库连接及迁移头。

设备凭据保存在 Electron `app.getPath('userData')/session.enc`，由操作系统加密，不能移植到其他 OS 用户。默认本机 owner 会话 30 天有效。过期后可重新运行 `pair`，按原工作空间身份配对；未确认操作继续保留。不要手工删除有待确认操作的桌面数据目录。

## 合同变更

修改 `backend/src/video_generation/contracts/` 中的类型，运行 `contracts`，提交 OpenAPI、JSON Schema 与 `api.generated.ts` 的差异。更新 `contracts/samples.json`，使同一有效/无效样例同时通过 Python/Pydantic、JSON Schema 和 TypeScript/Ajv 检查。

类型生成保留请求字段的可选默认值；更新请求至少包含 title / archived 之一，由运行时合同再次验证。业务写请求不接受额外身份字段、null 标题、字符串布尔值或布尔版本号。

## 验证范围

- Python：真实 PostgreSQL 上的 20 并发重试、ID 冲突、竞争修改、持久化拒绝、归档/恢复、事件分页与缺口、跨租户与跨 actor 访问、角色限制、配对重放、登出、分页和 API 重建；加上合同样例及适配端口 Fake。
- TypeScript：共用合同样例、IPC 方法/参数白名单和本机服务地址校验。
- Electron：实际窗口的配对、CRUD、冲突比较、sandbox、拒绝其他 WebContents 来源、离线提示；注入一次“真实提交后丢失响应”，关闭桌面和 API，再启动并校验无重复项目。

测试使用独立 `video_generation_test` 数据库，准备脚本仅创建和迁移，不删除数据库。测试使用随机 ID，允许重复执行。测试库中会保留验收数据；不要把它当作日常创作库。E2E 使用端口 18000 和 `runtime/verification/desktop-*` 独立凭据目录，仅停止自己启动的子进程。截图与日志位于 `runtime/verification/`，不进入 Git。

验证 Windows 目录构建时，可指定：

```powershell
$env:VIDEO_DESKTOP_EXECUTABLE = (Resolve-Path 'frontend/release/win-unpacked/Video Generation.exe').Path
pnpm --dir frontend test:e2e
Remove-Item Env:VIDEO_DESKTOP_EXECUTABLE
```

精确测试结果与环境版本见 [验证记录](verification.md) 和 [发布清单](../release-manifest.json)。B1 新增真实 Temporal 与进程崩溃恢复验证，仍不包含 GPU / LLM 实测。详见 [B1 说明](b1-first-part.md)。

## 常见问题

**Docker 连接失败**：启动 Docker Desktop，等引擎就绪后重试 `infra`。5432 已被占用时，先检查已有服务；不要覆盖其他 PostgreSQL 实例。

**修改密码后无法连接数据库**：`POSTGRES_PASSWORD` 仅在空卷初始化时生效。已有卷请使用数据库管理方式修改角色密码，并同步 `.env`；不要删除卷解决密码问题。

**Windows 异步连接失败**：使用 `video-api` 启动入口。它使用 SelectorEventLoop，供 psycopg 异步驱动工作。不要直接用默认 Uvicorn 入口替代；迁移、管理 CLI 与测试也使用相同循环工厂。

**配对码失效**：每次 `pair` 会使前一枚尚未使用的配对码失效；已配对设备不受影响。重新生成后在 10 分钟内使用。

**出现“结果待确认”**：恢复服务连接，点击恢复操作；客户端会查询原命令。不要用新命令重做相同操作。身份过期时重新配对原身份后再恢复。

**系统加密不可用 / session 无法解密**：恢复原 OS 用户的凭据环境和数据文件。应用拒绝降级成明文存储。此版本主要验收 Windows；Linux 需可用的系统密钥环，未做打包验收。

**关闭桌面后服务仍在运行**：这是预期行为，API 与数据库独立于桌面。终端 Ctrl+C 可停止 API；`docker compose --env-file .env -f deploy/video/compose.yaml stop` 可停止本项目数据库并保留数据卷。

## 当前交付边界

单机私有工作空间、项目管理、手动内容编辑与版本审批、可恢复模拟演练及目录构建。没有 installer / 签名 / 自动更新 / 后台系统服务，也没有用户邀请管理、媒体上传或真实视频导出。不得把本地开发配置直接用作公网多用户部署。

## B1 进程故障验证

`python -m uv run --project backend --frozen python scripts/verify_process_recovery.py --restart-temporal` 使用独立 `video_generation_faults_test` 数据库、18002 端口和 `video-process-tests` namespace。它会故意终止自己创建的 API、投递器与 Worker，并重启本仓库的 Temporal / Temporal PostgreSQL 容器；不要与其他 Temporal 验证同时运行。仅测试库允许启用精确操作 ID 的进程故障注入，默认关闭。报告写入 `runtime/verification/process-recovery/result.json`。
