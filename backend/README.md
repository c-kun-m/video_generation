# Python 后端与 PyCharm

可以直接把本目录 `backend` 当作 PyCharm 项目打开。后端使用标准的 `src` 包布局：`video_generation` 是可安装包，`src` 是源码容器。

## 配置一次即可

1. 在 **backend 目录**的终端执行 `python -m uv sync --frozen`，安装锁定依赖，并把本项目可编辑安装到 `.venv`。
2. PyCharm 的 Settings → Python Interpreter 选择**已有解释器** `backend/.venv/Scripts/python.exe`，不另外创建空环境。
3. 右键 `src` → Mark Directory as → Sources Root，供编辑器理解源码结构。不要把 `video_generation` 本身标成 Sources Root。
4. Run → Edit Configurations 使用本目录 `.run/` 中的 **Video API**、**Video Pair Device**、**Video Migrate**。如果 IDE 尚未自动显示，重新打开项目，或按下表新建 Python 配置。

| 配置项 | API | 配对 | 迁移 |
|---|---|---|---|
| 目标类型 | Module name | Module name | Module name |
| 模块 | `video_generation` | `video_generation` | `alembic` |
| Parameters | `serve` | `init-owner` | `-c alembic.ini upgrade head` |
| Working directory | 当前 `backend` 目录 | 当前 `backend` 目录 | 当前 `backend` 目录 |
| Interpreter | 项目 `.venv` | 项目 `.venv` | 项目 `.venv` |

包安装后不需要通过 IDE 的 Add content/source roots to PYTHONPATH 才能启动；共享配置将它们关闭，避免用 IDE 路径补丁掩盖缺失的安装。源码标记只用于编辑器导航和分析。个人 `.idea` 设置不进入 Git。

首次使用仍需根目录的 `.env`、已启动的 PostgreSQL 和数据库迁移，见 [完整启动说明](../README.md)。当前配置通过 `config.py` 所在位置定位仓库根目录的 `.env`，**不按运行工作目录查找**。不要复制一份密码配置到 `backend/.env`。

## 终端与调试等价启动

在本目录执行：

```powershell
python -m uv run --frozen python -m video_generation serve
# 或直接使用 PyCharm 选中的解释器
.\.venv\Scripts\python.exe -m video_generation serve
```

管理命令：

```powershell
.\.venv\Scripts\python.exe -m video_generation init-owner
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
```

已有的 `video-api` / `video-admin init-owner` 入口继续可用。也支持 `python -m video_generation.cli serve`。直接右键运行 `cli.py` 时须设置参数 `serve`；不提供参数会显示所需子命令，不会自动开始服务或签发凭据。

API 的启动路径统一进入 `serve()`，保留 Windows / psycopg 所需的 SelectorEventLoop。请不要绕过该入口启动默认 Uvicorn 事件循环。

## 常见错误

B1 新增 **Video Temporal Worker**、**Video Outbox Dispatcher**、**Video Initialize Temporal** 共享配置，模块仍为 `video_generation`，参数分别为 `worker`、`dispatcher`、`init-temporal`。保持同一 `.venv` 解释器和 `src` Sources Root；先运行根目录 `scripts/dev.ps1 infra`。完整用法见 [B1 第一部分](../docs/b1-first-part.md)。

- `No module named video_generation`：检查运行配置的解释器是否就是 `.venv`，并重新执行 `uv sync --frozen`。仅把 Working directory 改为仓库根目录不能替代包安装。
- `No module named uvicorn / sqlalchemy`：运行配置使用了另一套未安装依赖的 Python。
- 编辑器导入标红而运行正常：检查 `src` 的 Sources Root 标记，重新选择正确解释器并等待索引完成。
- `the following arguments are required: command`：设置参数 `serve` / `init-owner`，或选择对应共享配置。
- `/health/ready` 返回 503：检查 Docker 和迁移；这与 Python 导入根目录是两个不同问题。

参考：[PyCharm Python 运行配置](https://www.jetbrains.com/help/pycharm/run-debug-configuration-python.html)、[PyCharm Sources Root](https://www.jetbrains.com/help/pycharm/project-structure-dialog.html)、[Python Packaging 的 src 布局](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)。
