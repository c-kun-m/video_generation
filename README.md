# Video Generation

文本驱动的视频生产项目，目标是完成需求、剧本、配音、分镜、镜头生成、审片、局部重做和成片导出。

第一阶段工程已实现：**Python / FastAPI / PostgreSQL 后端 + Electron / React 桌面端**，支持设备配对、项目创建、查询、重命名、归档和恢复。命令具有幂等去重、版本冲突检查和断线恢复能力。

LangChain、Temporal、ComfyUI 和 FFmpeg 的真实创作链路属于后续阶段，当前能力页面会显示“尚未接入”。本次交付不代表 B0–B4 或真实视频生成验收完成。

- [开发文档入口：G00–G17](视频生产开发文档/README.md)
- [技术选型与 ComfyUI 对接方案](技术选型与ComfyUI对接方案.md)
- [第一阶段架构、范围与验收](docs/phase-one.md)
- [运行、测试与故障排查](docs/development.md)
- [直接在 PyCharm 打开 backend](backend/README.md)

## 本机启动（Windows / PowerShell）

准备 Python 3.12、Node.js 24、pnpm 11、uv 和已启动的 Docker Desktop。依赖精确版本见锁文件；本机验证版本见 [release-manifest.json](release-manifest.json)。如果没有 uv，可运行 `python -m pip install --user uv`。

在项目根目录执行：

```powershell
.\scripts\dev.ps1 setup
.\scripts\dev.ps1 infra
.\scripts\dev.ps1 migrate
.\scripts\dev.ps1 pair
```

`setup` 自动生成本机数据库密码，不覆盖已有 `.env`。`pair` 会显示 10 分钟有效的一次性配对码。

分别打开两个终端：

```powershell
# 终端 1：保持后端运行
.\scripts\dev.ps1 backend
```

```powershell
# 终端 2：启动桌面，在配对页面输入刚才的配对码
.\scripts\dev.ps1 desktop
```

开发桌面占用 `127.0.0.1:5173`，API 使用 `127.0.0.1:8000`，PostgreSQL 使用 `127.0.0.1:5432`。关闭桌面不会停止后端或数据库。

## 构建与验证

```powershell
.\scripts\dev.ps1 test       # PostgreSQL + Python + TypeScript 单元/集成检查
.\scripts\dev.ps1 test-e2e   # 实际 Electron 窗口；独立测试库、API 端口 18000
.\scripts\dev.ps1 package    # 可运行 Windows 目录构建
```

构建入口：`frontend/release/win-unpacked/Video Generation.exe`。整个 `win-unpacked` 目录须一起保留。后端仍需独立启动；这是未签名的目录构建，安装程序、自动更新和系统服务不在本阶段范围内。构建产物不上传 Git。

## 目录

```text
frontend/                 Electron Main / Preload、React 页面与桌面测试
backend/src/video_generation/
  api/                    FastAPI HTTP 边界、身份校验、健康检查
  domain/                 项目、配对、命令幂等与事件逻辑
  storage/                SQLAlchemy 模型、会话工厂
  contracts/              Pydantic 合同与导出入口
  adapters/               Agent / Render / Media / Storage Protocol
backend/migrations/       Alembic 迁移
contracts/                导出的 OpenAPI、JSON Schema、跨语言测试样例
deploy/video/             固定镜像摘要的 PostgreSQL Compose
scripts/                  Windows 开发入口与测试数据库准备
docs/                     本次实际实现及运行说明
视频生产开发文档/          完整产品设计 G00–G17
```

采用 Python 后端：FastAPI、LangChain Python、Temporal Python SDK、PostgreSQL / SQLAlchemy / Alembic；前端使用 React / TypeScript / Electron，视频生成与合成使用 ComfyUI 和 FFmpeg。具体职责、接口、恢复规则与开发顺序见选型方案。

原开发文档引用的 `UI开发/`、`开发文档/`、`upstream.lock.json` 和原桌面工程未包含在本仓库；这些历史引用不代表对应工程已存在。2026-09-07 已按用户选择同步修订为 Python 后端方案，此前版本可从 Git 历史查看；设计文档不代表功能已实现。

模型权重、运行数据和凭据保存在 Git 之外。工作流 API JSON、参数绑定和依赖摘要应纳入版本控制。
