# openubmc-debug 概览

## 适用场景
- 用户提供 BMC IP，需要查看 app.log/framework.log
- 需要 busctl/mdbctl(DBus) 对象/属性查询
- 需要结合本地代码 + 现场证据给出分析结论

## 目录结构
- `SKILL.md`：主流程与策略
- `scripts/`：日志与 DBus 采集脚本
- `references/`：环境/日志/组件速览等参考

## 典型输出结构
- 现象总结
- 证据日志与证据块（命令 + 原始输出）
- 环境快照（BMC 时间/uptime/固件版本）
- 可能涉及组件 + 代码路径
- 初步结论 + 下一步验证建议

## 注意事项
- SSH 只用于对象/DBus 查询，Telnet 用于日志
- 信息不足时先补证据，再给结论
