# openubmc-developer 概览

## 适用场景
- 功能实现或行为变更
- 可提供 SSH/Telnet 环境以验证 DBus/日志
- 需要输出 Obsidian 详细设计

## 目录结构
- `SKILL.md`：主流程与策略
- `references/`：组件速览与环境/日志参考
- `scripts/`：日志与 DBus 采集脚本

## 典型流程
1. 需求澄清与最小输入集
2. NotebookLM 预查询 + 快速失败
3. SSH/Telnet 现场验证
4. 影响面梳理 + Plan 模板
5. 方案确认后再开发
6. 构建/测试与验证
7. 输出 Obsidian 设计文档

## 注意事项
- 变更 MDS 必须重新生成代码，禁止手改 `gen/`
- 变更北向行为需说明兼容与回滚
