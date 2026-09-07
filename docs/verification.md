# 第一阶段验证记录

日期：2026-09-07。环境：Windows 11 x64、Python 3.12.6、Node 24.19.0、pnpm 11.19.0、uv 0.12.10、Docker Engine 29.2.1。依赖与镜像摘要见根目录 `release-manifest.json`。

| 检查 | 结果 |
|---|---|
| `dev.ps1 setup / check / migrate` | 成功；首次迁移和重复迁移均成功 |
| Ruff 检查与格式检查 | 通过，26 个 Python 文件 |
| pytest | 19 passed，真实独立 PostgreSQL 测试库 |
| TypeScript `tsc --noEmit` | 通过 |
| Prettier | 通过 |
| Vitest | 18 passed，2 个测试文件 |
| 生产资源构建 | Main / Preload / React 构建成功 |
| Electron 端到端流程 | 通过：项目管理、冲突、断线与 API/桌面重启恢复 |
| Windows 目录构建 | `Video Generation.exe` 构建成功，并以该可执行文件通过完整桌面端到端测试 |
| 开发 HMR 入口 | `electron-vite dev` 实际窗口加载成功，配对页面可见，Video Bridge 调用成功 |
| 合同重生成 | JSON Schema、OpenAPI、生成的 TypeScript 重生成前后 SHA-256 一致 |
| 数据库容器重启/重建 | 保留同一命名卷；24 个已有测试项目的内容摘要在前后完全一致 |
| 页面检查 | 查看真实窗口的项目库、详情、首次配对截图，无重叠或缺失控件 |

其中数据库集成验证包含 20 个相同命令并发只产生 1 个项目、1 个事件及 1 条命令结果；另验证冲突拒绝持久化、越权访问受限及事件缺口要求快照重载。

桌面端到端验证在真实 API 成功提交后主动丢弃一次响应，再关闭 API 与桌面，确认重启后按原命令恢复，项目没有重复创建。另从测试创建的其他 WebContents 发起 IPC，验证返回 `FORBIDDEN`。

截图与运行日志保存在本机 `runtime/verification/`；其中项目名称是独立测试数据库中的验收数据。测试产物和可执行构建不进入 Git。

本次没有执行模型推理、ComfyUI 工作流、Temporal workflow、FFmpeg 合成、安装包签名、公网或多机部署测试，界面也未宣称这些能力可用。

## PyCharm 启动入口修复（2026-09-07）

补齐 `python -m video_generation serve` 和直接运行 `cli.py` 的入口，保留已有 console scripts。新增测试覆盖根目录 / backend 两个工作目录、三种 CLI 入口、无参数不执行管理操作及 serve 分发；后端测试结果为 **27 passed**，Ruff 通过。从 backend 目录实际启动 API 后，PostgreSQL `/health/ready` 检查通过。

共享 `.run` 配置已提供，解释器与模块启动命令已验证；未自动操作 PyCharm 窗口进行 IDE 原生调试验收。上面的 Windows 桌面构建记录仍对应第一阶段构建，本次没有变更桌面代码。
