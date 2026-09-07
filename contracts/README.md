# 跨进程合同

源模型在 `backend/src/video_generation/contracts/models.py`。运行根目录 `scripts/dev.ps1 contracts` 后，本目录生成 JSON Schema 2020-12 与 OpenAPI 3.1，前端生成 `src/shared/api.generated.ts`。不要直接编辑生成文件。

`samples.json` 是 Python 与 TypeScript 共用的有效/无效请求样例。身份字段由服务端会话产生，业务写请求禁止额外 tenant / actor 字段。复杂的“至少一项修改”规则同时包含在 JSON Schema 与 Python 验证器中。

当前合同版本为 `/video/v1`，只覆盖第一阶段项目管理；后续新增内容、审批和渲染合同时另行评审兼容性。
