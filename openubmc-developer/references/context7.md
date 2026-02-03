# Context7 openUBMC 文档

当本地代码 + 环境日志/对象信息不足时，使用 Context7 查询官方文档。

## 先 resolve library ID
必须先调用 `resolve-library-id`，关键词用 `openUBMC`。
优先候选（覆盖面高）：
- `/websites/openubmc_cn_zh_development`

备用：
- `/openubmc-doc/openubmc-doc`

## 示例查询（query-docs）
- "busctl usage in openUBMC"
- "mdbctl command reference"
- "app.log framework.log meaning"
- "hwproxy hwdiscovery general_hardware component mapping"

解析完成后，用 `query-docs` 和选定的 library ID 进行检索。
