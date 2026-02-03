# openUBMC source/ 组件概览

本参考整理 `/home/workspace/source/` 下的顶层组件。

- `account/`：用户/账户管理与鉴权策略，角色权限、登录规则、备份与导入导出。
- `bingo/`：openUBMC CLI 工具链，用于组件开发、生成、构建、测试与打包。
- `bios/`：BIOS 配置/证书管理、固件升级（含无感）、PFR 自愈。
- `chassis/`：机箱状态、入侵/UID、LED 控制、设备数量统计与机箱度量数据。
- `fructrl/`：上下电控制（开/关/复位）、电源锁与上电策略。
- `frudata/`：FRU/Eeprom 解析与统一读写接口（标准/非标准）。
- `general_hardware/`：板卡级硬件服务与固件升级支持。
- `hica/`：子系统启动编排（skynet/systemd 配置与入口代码）。
- `lsw/`：交换板配置与驱动，VLAN/端口与内外网通信。
- `manifest/`：产品集成配置仓，构建/打包与开发环境初始化。
- `manufacture/`：装备测试项管理、路由分发与版本信息获取（IPMI）。
- `mdb_interface/`：MDB/D-Bus 资源协作接口模型定义（MDS）。
- `network_adapter/`：网卡/网口/光模块信息与 NCSI/MCTP/LLDP 协议处理。
- `observability/`：可观测性服务（日志/指标/链路追踪，OpenTelemetry）。
- `pcie_device/`：PCIe 拓扑管理、设备纳管、高速链路/线缆检测。
- `power_mgmt/`：电源信息/健康、模式管理、固件升级与黑匣子日志。
- `profile_schema/`：配置导入导出与定制化 schema 定义。
- `rack_mgmt/`：机柜节点管理（LLDP U位）、心跳与网络策略。
- `rackmount/`：北向接口映射配置（Redfish/CLI/SNMP/web_backend）。
- `rootfs_user/`：rootfs 用户配置与启动脚本。
- `scripts/`：仓库辅助脚本（如 mdbctl 循环读取）。
- `sensor/`：传感器管理、门限/健康与 SEL 事件。
- `storage/`：RAID/控制器/硬盘/逻辑盘管理与健康检测。
- `thermal_mgmt/`：风扇/液冷/泵/阀管理与散热策略。
- `vpd/`：CSR/PSR 与厂商差异化数据。
- `webui/`：Web UI 前端（Vue 3 + Vite + Element Plus/OpenDesign）。
