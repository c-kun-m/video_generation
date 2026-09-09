# 使用 YAML 启动项目

根目录 `startup.yml` 决定启用哪些组件、执行什么命令和按什么顺序启动。Python 的 CLI 保留单进程执行入口，YAML 统一启动器负责读取配置和管理进程。

## 启动

第一次安装或拉取新增依赖后，在根目录运行 `./scripts/dev.ps1 setup`。之后只需：

```powershell
cd D:\project\video_generation
.\scripts\dev.ps1 start
```

默认会执行 `prepare.infrastructure`（Docker 基础服务）、`prepare.temporal_namespace`（Temporal namespace）及 `prepare.migrations`（业务数据库迁移），成功后顺序启动 API、Dispatcher、Worker、Electron 桌面。Docker Desktop 需要已经启动。首次配对在另一个终端运行 `./scripts/dev.ps1 pair`。

PyCharm 只打开 `backend` 时，可以选择 **Video Project**；解释器仍使用该目录 `.venv`。等价命令是 `python -m video_generation start`。配置和命令工作目录按仓库根目录解析，不依赖 IDE 的当前目录。

保持统一启动器运行。关闭桌面不会停止其他后台进程；Ctrl+C 或停止启动器会结束本次拥有的进程树，Docker 数据服务继续运行。Windows 使用 Job Object 管理所有后代进程，包括 PowerShell、pnpm 和 Electron。强制停止后，未完成制作保留持久化状态，重新启动 Worker 后恢复；停止启动器不等于发送业务取消命令。

## 配置

例如，只修改默认文件中 Worker 的开关：

```yaml
services:
  worker:
    enabled: false
    command: ["{python}", "-m", "video_generation", "worker"]
```

这段是配置片段，修改原文件对应项即可。关闭 Worker 后，编辑和审批仍可使用；没有其他 Worker 处理同一任务队列时，制作会等待执行。要暂时由 PyCharm 单独调试 API/Worker，可关闭对应项后运行原有 **Video API** / **Video Temporal Worker** 配置。

| 字段 | 含义 |
|---|---|
| `version` | 配置格式版本，当前为 `1` |
| `prepare` | 按书写顺序执行的一次性准备命令；非零退出或超时则停止后续启动 |
| `services` | 按书写顺序启动的常驻服务 |
| `enabled` | 是否执行该项，使用 YAML 布尔值 `true` / `false` |
| `command` | 命令参数数组，不能写成单个 shell 字符串；需要 shell 功能时明确调用 PowerShell 脚本 |
| `cwd` | 工作目录，相对于仓库根目录，默认 `.`，必须位于仓库内 |
| `timeout_seconds` | 准备命令执行时限，或服务启动就绪检查时限；不是制作任务时限 |
| `ready_url` | 可选本机 HTTP 检查地址，返回 200 才启动后面的服务；端口已占用则停止启动，不接管已有进程 |
| `stop_project_on_exit` | 常驻服务退出时是否结束其他受管理服务，默认 `true`；桌面为 `false` |

命令可以使用 `{python}`（当前项目解释器）、`{powershell}`（已安装的 PowerShell）和 `{api_url}`（当前 API 本机地址）占位符。应用参数和密码继续由 `.env` / 环境变量管理。修改开关后重新启动生效，不提供热加载。

未配置 `ready_url` 的 Worker 和 Dispatcher 只确认进程已启动；是否已连接 Temporal 请查看桌面的服务心跳或进程日志。它们本身会重试连接。当前配置没有服务自动重启策略，核心进程退出时启动器报错并清理本次进程，便于发现启动错误。

## 校验与日志

```powershell
# 只检查配置，不执行任何命令
.\scripts\dev.ps1 start -Check

# 使用另一份配置，路径相对于仓库根目录
.\scripts\dev.ps1 start -Config runtime/startup.local.yml
```

每次日志单独保存在 `runtime/launcher/<时间与唯一后缀>/`。准备步骤有 `prepare-infrastructure.log`、`prepare-temporal_namespace.log`、`prepare-migrations.log`；服务分别有 `api.log`、`dispatcher.log`、`worker.log`、`desktop.log`。错误消息给出具体日志路径。日志不提交 Git。

同一个项目只允许一个统一启动器运行。手工启动的服务不会被接管或关闭；端口占用时，停止手工进程或禁用对应配置再启动。关闭全部 `services` 会报告配置错误。

YAML 使用 SafeLoader 读取并校验重复键、未知字段和字段类型；它仍然是可以启动本机程序的开发配置，应只运行自己维护的命令。实现依据：[PyYAML 数据加载说明](https://pyyaml.org/wiki/PyYAMLDocumentation)、[Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)。

## 本轮验证（2026-09-09）

后端全量 69 项、前端 Vitest 30 项通过；Ruff、TypeScript 和 Prettier 通过。新增启动器测试覆盖禁用服务、无效 YAML、准备失败、端口占用、就绪超时、重复启动、可选桌面退出、核心进程退出和 Windows 后代进程清理。根目录及只打开 `backend` 的启动检查均通过，包括激活虚拟环境后从 PowerShell 启动。

使用独立 `video_generation_launcher_test` 数据库及测试队列，实际通过 `scripts/dev.ps1 start` 读取默认 YAML：API 与桌面开发服务器就绪，Worker 和 Dispatcher 均写入心跳；结束本次测试进程后，18004 / 5173 端口释放，Docker 数据服务继续运行。记录见 [启动验证报告](../evidence/reports/yaml-startup.json)。本次新增开发启动方式，未重新打包桌面发行物；根目录 `release-manifest.json` 继续对应 2026-09-08 的 v0.2.0 构建，新增依赖见当前 `backend/uv.lock`。
