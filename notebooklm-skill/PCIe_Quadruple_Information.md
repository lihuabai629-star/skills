# openBMC 中的 PCIe 四元组信息获取流程

在 openBMC 中，PCIe 四元组（Quadruple）信息（即 VendorID, DeviceID, SubVendorID, SubDeviceID）本质上来源于 PCIe 设备本身的硬件配置空间（Configuration Space）。

BMC 获取这组信息的流程并非直接读取，而是通过与 BIOS 和带内管理单元（PMU/IMU）的交互完成的。具体流程如下：

## 1. 信息的物理来源

四元组是烧录在 PCIe 设备（如网卡、RAID 卡、GPU 等）芯片内部的只读标识信息，用于唯一标识设备的型号和制造商：

*   **Vendor ID**: 制造商 ID（如 Intel, NVIDIA, Huawei 等）。
*   **Device ID**: 设备 ID（具体芯片型号）。
*   **Subsystem Vendor ID**: 子系统制造商 ID。
*   **Subsystem Device ID**: 子系统设备 ID。

## 2. 获取流程（BMC 如何拿到）

BMC 位于带外，无法直接扫描 PCIe 总线，因此依赖 BIOS 和 PMU/IMU（带内管理单元）的协助。

1.  **BIOS 枚举与 BDF 分配**：服务器启动（POST）时，BIOS 扫描 PCIe 总线，为每个在位的 PCIe 设备分配逻辑地址，即 BDF (Bus, Device, Function)。
2.  **BIOS 上报 BDF 给 BMC**：BIOS 通过 OEM IPMI 命令（如 `WritePcieCardBdfToBmc` / `Set PCIe Card BDF`）将物理槽位（Slot ID）与逻辑地址（BDF）的对应关系发送给 BMC 的 `pcie_device` 组件。
3.  **BMC 发起查询请求**：BMC 收到 BDF 后，无法直接通过 BDF 知道设备是谁。因此，BMC 的 `pcie_device` 组件会使用这个 BDF 作为索引，向 PMU (Performance Monitoring Unit) 或 IMU (Inertial Measurement Unit，此处指带内管理单元) 发起查询请求。
4.  **PMU/IMU 读取并返回四元组**：PMU/IMU 具备带内访问 CPU PCIe Root Complex 的能力。它根据 BMC 提供的 BDF 地址，通过 PCIe 总线直接读取该设备的配置空间寄存器，获取 四元组信息，并将其返回给 BMC。

## 3. 四元组的作用

BMC 拿到四元组后，主要用于 **加载正确的硬件配置文件（CSR）**。

*   **文件名拼接**：BMC 将四元组拼接成 ID 和 AuxID，生成目标 CSR 文件名。格式通常为：`Bom_DeviceID+VendorID_SubDeviceID+SubVendorID.sr`（例如 `14140130_100010e2_10004010.sr`）。
*   **设备上线**：BMC 加载匹配的 CSR 文件，生成 `PCIeCard`、`NetworkAdapter` 等对象，从而实现对该设备的监控（温度、健康状态）和管理。

## 总结

四元组来自 PCIe 卡硬件本身。BMC 的获取路径是：**BIOS 上报地址 (BDF) -> BMC 拿着地址问 PMU -> PMU 读硬件寄存器返回四元组 -> BMC 接收**。