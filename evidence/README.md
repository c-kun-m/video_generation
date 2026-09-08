# B1 第一部分证据索引

本轮交付的具体范围与验收结论见 [B1 验收记录](../docs/b1-verification.md)。`features/` 使用原开发文档功能 ID；每个记录列出已验证子集、实现/测试路径、设计摘要和剩余范围。原功能超出本轮范围时仍标记 `IMPLEMENTING`，不把模拟演练的完成等同于整个功能或 B1 完成。

`reports/` 保存不含凭据的进程恢复报告、迁移报告，以及本轮检查结果和文件 SHA-256。大型日志、数据库备份、桌面凭据、截图和构建只保留在本机 `runtime/` 或 `frontend/release/`，不提交 Git。

精确依赖与构建摘要见 [release-manifest.json](../release-manifest.json)。证据中的 `source_base_commit` 指本轮修改前的提交；实现文件摘要和包含这些文件的 Git 提交共同标识被测代码，不把旧提交当作新实现的提交。
