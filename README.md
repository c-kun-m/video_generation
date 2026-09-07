# Video Generation

文本驱动的视频生产项目，目标是完成需求、剧本、配音、分镜、镜头生成、审片、局部重做和成片导出。

当前处于设计与技术选型阶段，尚无应用代码，也未进行真实视频生成验收。

- [开发文档入口：G00–G17](视频生产开发文档/README.md)
- [技术选型与 ComfyUI 对接方案](技术选型与ComfyUI对接方案.md)

建议采用 React / Electron、TypeScript / Fastify、LangChain JS、Temporal、PostgreSQL、ComfyUI 和 FFmpeg。具体职责、接口、恢复规则与开发顺序见选型方案。

原开发文档引用的 `UI开发/`、`开发文档/`、`upstream.lock.json` 和原桌面工程未包含在本仓库；这些历史引用不代表对应工程已存在。原稿保留，选型补充单独记录，不将设计文档标记为已实现。

模型权重、运行数据和凭据保存在 Git 之外。工作流 API JSON、参数绑定和依赖摘要应纳入版本控制。
