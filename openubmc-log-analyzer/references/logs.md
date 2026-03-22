# openUBMC Log Reference

Last updated: 2026-02-06
Source: NotebookLM (openUBMC architecture notebook) + local bundle inventory (openUBMC_20260204-0112.tar)

## Directory Meaning

- LogDump
  - Core runtime logs aggregated across system and business components.
  - First stop for most functional or operational failures.
- AppDump
  - Per-component private logs and MDB state snapshots.
  - Best for data-not-updating, object missing, or component-specific failures.
- RTOSDump
  - OS-level state, systemd logs, kernel/driver info.
  - Best for service start failures, kernel/driver errors, disk full, or boot issues.
- OSDump
  - Serial/console recordings, often host OS or boot stage.
- SpLogDump
  - Platform/version or special logs (varies by platform).
- BMALogDump
  - Host agent / in-band logs (iBMA/host agent), used when host-side data missing.
- DeviceDump
  - Device-specific low-level logs or register snapshots.

## LogDump Files

- app.log
  - Module: business components (non-framework) such as sensor, firmware_mgmt, pcie_device, bios.
  - Content: component runtime logs (DEBUG..ERROR), business flow, error details.
  - Use: primary log for functional issues and component errors.
- framework.log
  - Module: framework layer (maca, hwdiscovery, hwproxy).
  - Content: service start/stop, health check, CSR object load/unload, process crash/respawn.
  - Use: startup failures, component crashes, hardware discovery or proxy failures.

### LogDump/framework/ directory

- Note: NotebookLM documents only `framework.log` as a file in LogDump. It does NOT define a `LogDump/framework/` directory. If such a directory exists in a bundle, treat it as platform-specific and query NotebookLM before adding meanings.
- operation.log
  - Module: operation_logger / oms.
  - Content: user operations (login, IPMI commands, configuration changes).
  - Use: audit trail: who/when/what changed.
- security.log
  - Module: security/iam/user management.
  - Content: login/auth results, account lock, cert/signature verification failures.
  - Use: login failures, authentication/authorization issues.
- maintenance.log
  - Module: maintenance.
  - Content: maintenance events and fault codes.
  - Use: maintenance history and related issues.
- running.log
  - Module: system monitor.
  - Content: system runtime anomalies, key process events, resource status.
  - Use: long-running health and stability monitoring.
- sensor.log
  - Module: sensor.
  - Content: sensor events, SEL records, read failures.
  - Use: sensor read failures, health alarms, SEL investigations.
- alarm.log
  - Module: event/alarm.
  - Content: alarm assert/deassert lifecycle and values.
  - Use: alarm lifecycle analysis and object correctness.
- cooling_control.log
  - Module: cooling / thermal_mgmt.
  - Content: fan control strategy computations, target PWM/Duty values.
  - Use: fan speed anomalies or thermal strategy debugging.
- Thermal.log
  - Module: thermal_mgmt (often in AppDump/thermal_mgmt).
  - Content: thermal debug (temperature sampling, PID logic, thermal policy).
  - Use: thermal policy and over-temp protection debugging.
- bmc_health.log
  - Module: bmc_health.
  - Content: CPU/memory usage stats, including startup stage.
  - Use: performance bottlenecks, high CPU/memory usage.
- ps_black_box.log
  - Module: power_mgmt.
  - Content: PSU black-box data (register snapshots at fault).
  - Use: deep PSU hardware fault analysis.
- net_stream.log
  - Module: network stack / bmc_network.
  - Content: network traffic summaries or protocol interactions.
  - Use: network connectivity or protocol issues.
- hw_stream.log
  - Module: hwproxy / driver.
  - Content: bus traffic (I2C/PCIe) interactions.
  - Use: hardware bus timeout/data errors.
- mc_stream.log
  - Module: micro-component communication.
  - Content: inter-component RPC flow.
  - Use: cross-component call debugging.

### Additional observed in sample bundle (name-based, verify if needed)

- dmesg_info
  - Content: kernel ring buffer logs (dmesg snapshot).
  - Use: filesystem errors, OOM, hardware/driver issues.
- linux_kernel_log*
  - Content: driver layer logs (more detailed than dmesg).
  - Use: I2C/SMBus, NCSI, PCIe link issues.
- cpumem_usage_info_dump.csv
  - Content: historical CPU/memory usage statistics.
  - Use: performance bottlenecks and spikes.
- mem_info_*.csv
  - Content: memory usage breakdown (RSS/Slab/PageTables, etc.).
  - Use: memory pressure or leak trends.
- remote_log
  - Content: KVM/remote console session and virtual media logs.
  - Use: KVM black screen, VMM mount failure, USB emulation issues.
- LSI_RAID_Controller_Log
  - Content: RAID controller firmware logs (LSI/Broadcom).
  - Use: RAID card detection, drive drop, controller errors.
- netcard/netcard_info.txt
  - Content: NIC inventory and status (vendor/model/optics, link state).
  - Use: NIC/optical module detection issues, data mismatch with OS.
- pciecard/*/error_log_*.bin
  - Content: PCIe device firmware error logs (binary).
  - Use: SmartNIC/DPU/NPU firmware crash analysis (vendor decode).
- pciecard/*/operate_log_*.bin
  - Content: PCIe device operation logs (binary).
  - Use: device behavior timeline before failure (vendor decode).
- storage/ctrllog
  - Content: RAID controller firmware logs.
  - Use: RAID init failures, drive drop, controller errors.
- storage/drivelog/*/SMARTAttribute
  - Content: disk SMART attributes snapshot.
  - Use: disk health and pre-failure indicators.
- storage/drivelog/*/SATA_Log
  - Content: SATA log data (errors/transport).
  - Use: link quality and transport errors.
- storage/phy/*/PHY_Error_Count.csv
  - Content: SAS PHY error counters (CSV).
  - Use: link stability, CRC/sync errors, cable/backplane issues.
- M3LogDump/m3_log
  - Content: BMC SoC M3 co-processor logs (power/reset/boot).
  - Use: BMC boot loops, power sequence, watchdog resets.

## AppDump Common Files (per component)

Located under dump_info/AppDump/<component>/

- rpc_records.log
  - Content: RPC request statistics and call counts for component interfaces.
  - Relation: D-Bus method call frequency (RPC over D-Bus).
  - Use: detect high-frequency polling or abnormal call patterns.
- sync_property_trace.log
  - Content: MDB property sync trace.
  - Relation: D-Bus PropertiesChanged/InterfacesAdded signals and initial fetch.
  - Use: data-not-updating issues; verify signals and initial fetch.
- mdb_info.log
  - Content: MDB object tree snapshot, persistence stats.
  - Use: verify CSR/object creation, missing objects, persistence status.

Component-specific:
- storage/raid_controller_lib.log
  - Content: RAID library/hardware interaction details (warnings/errors).
  - Use: RAID detection/config failures, low-level hardware communication issues.

### AppDump component mapping (typical use cases)

- sensor
  - Use: sensor read failures, missing SEL events, ID mismatches.
- power_mgmt
  - Use: PSU alarms, power readings fail, PSU blackbox collection.
- thermal_mgmt
  - Use: fan full-speed, PID strategy issues, temp control failures.
- network_adapter
  - Use: NIC/optics info missing, NCSI failures, link down.
- pcie_device
  - Use: PCIe device missing, topology mismatch, link training failures.
- storage
  - Use: RAID controller not detected, drive missing, RAID lib load errors.
- redfish
  - Use: Redfish API failures, data mapping issues.
- frudata
  - Use: FRU data empty/garbled, EEPROM read/write failures.
- bios
  - Use: BIOS config not applied, POST/boot stage anomalies.
- chassis
  - Use: LED/UID control failures, chassis intrusion, power-on lock.
- account / iam
  - Use: login failures, permission errors, role mapping issues.
- event / event_policy
  - Use: event missing/duplicate, alarm policy mismatch.
- observability
  - Use: metrics missing (CPU/mem charts), pipeline failures.
- rmcpd
  - Use: IPMI over LAN session failures.
- mctpd
  - Use: MCTP endpoint discovery failures (NVMe/PCIe devices).
- hwproxy
  - Use: I2C/SMBus/GPIO access failures, bus timeouts.
- hwdiscovery
  - Use: board not discovered, CSR/SR load failures.
- maca
  - Use: component startup check failed, frequent restarts.
- bmc_network
  - Use: IP/VLAN config errors, route issues.
- bmc_time
  - Use: NTP sync/time jump issues.
- bmc_upgrade
  - Use: upgrade task failure (verify/extract/apply).

## RTOSDump (sysinfo)

- sysinfo/journalctl.log* (journalctl.log, .1, .2, .3)
  - Content: systemd journal logs; service start/stop failures; kernel/driver messages.
  - Use: service start failures, repeated restart, kernel/driver errors.

### RTOSDump sysinfo details

- sysinfo/top_info
  - Content: top output snapshot.
  - Use: CPU/memory hot processes, system load spikes.
- sysinfo/ps_info
  - Content: process/thread snapshot.
  - Use: hung processes (D state), runaway forks.
- sysinfo/free_info
  - Content: memory usage summary.
  - Use: OOM or memory pressure analysis.
- sysinfo/vmstat
  - Content: virtual memory stats.
  - Use: swap thrash, IO waits, system performance.
- sysinfo/uptime / sysinfo/loadavg
  - Content: uptime and load averages.
  - Use: unexpected reboot detection, sustained overload.
- sysinfo/meminfo
  - Content: detailed memory breakdown.
  - Use: kernel memory leakage indicators.
- sysinfo/slabinfo
  - Content: slab allocator stats.
  - Use: kernel object leaks (inode/dentry growth).
- sysinfo/softirqs
  - Content: softirq counters.
  - Use: network or timer storm debugging.
- sysinfo/interrupts
  - Content: hardware interrupt counts.
  - Use: driver interrupt storm or hardware issues.
- sysinfo/modules
  - Content: loaded modules list.
  - Use: verify required kernel modules present.
- sysinfo/cmdline
  - Content: kernel boot parameters.
  - Use: boot mode / kernel parameter verification.
- sysinfo/df_info
  - Content: disk usage.
  - Use: disk full (/var/log, /data) causing failures.
- sysinfo/lsof_info
  - Content: open file handles.
  - Use: file handle leak or mount busy issues.
- sysinfo/diskstats
  - Content: disk IO statistics.
  - Use: IO bottleneck or flash wear analysis.
- sysinfo/partitions / sysinfo/mtd / sysinfo/filesystems
  - Content: partition tables, MTD layout, supported filesystems.
  - Use: storage layout and upgrade target verification.
- sysinfo/ipcs_s / sysinfo/ipcs_q / sysinfo/ipcs_s_detail
  - Content: System V IPC (semaphores, queues).
  - Use: IPC deadlock or queue backlog.
- sysinfo/locks
  - Content: kernel file locks.
  - Use: file lock contention or EAGAIN errors.
- sysinfo/uname_info / sysinfo/version / sysinfo/cpuinfo / sysinfo/devices
  - Content: kernel build, CPU, registered devices info.
  - Use: baseline OS/CPU/device verification.

### RTOSDump driver_info

- driver_info/veth_drv_info
  - Content: virtual ethernet driver state (host-bmc in-band).
  - Use: in-band channel down, host agent connectivity issues.
- driver_info/cdev_drv_info
  - Content: character device driver info (KCS/BT/SMIC channels).
  - Use: OS-side ipmitool/KCS interface failures.
- driver_info/edma_drv_info
  - Content: EDMA driver state for data movement.
  - Use: veth/data transfer failures or EDMA init errors.
- driver_info/kbox_info
  - Content: kernel blackbox crash snapshot.
  - Use: kernel panic or watchdog resets with little app log evidence.
- driver_info/lsmod_info
  - Content: loaded kernel module list.
  - Use: confirm required modules are loaded.
- driver_info/dmesg_info
  - Content: kernel ring buffer output.
  - Use: low-level driver/hardware errors.

### RTOSDump networkinfo

- networkinfo/services
  - Content: network services mapping or status.
  - Use: verify expected services/ports.
- networkinfo/resolv.conf
  - Content: DNS configuration.
  - Use: domain resolution failures.
- networkinfo/dhclient*.conf
  - Content: DHCP client config/lease.
  - Use: DHCP IP acquisition issues.
- networkinfo/iptables_nat_info / ip6tables_nat_info
  - Content: NAT rules for IPv4/IPv6.
  - Use: port forwarding or NAT failures.
- networkinfo/netstat_info
  - Content: listening ports and active connections.
  - Use: verify SSH/HTTPS/IPMI listening, abnormal connection counts.
- networkinfo/route_info
  - Content: routing table.
  - Use: cross-subnet routing errors or wrong default route.
- networkinfo/ifconfig_info
  - Content: interface configuration and stats.
  - Use: link up/down, RX/TX errors.

### RTOSDump versioninfo

- versioninfo/server_config.txt
  - Content: server model/config baseline.
  - Use: environment baseline verification.
- versioninfo/package_info
  - Content: installed packages list.
  - Use: version mismatch/compatibility checks.
- versioninfo/RTOS-Revision / RTOS-Release
  - Content: OS revision and release numbers.
  - Use: driver compatibility checks.
- versioninfo/app_revision.txt
  - Content: BMC app/component versions.
  - Use: verify running app baseline.

### RTOSDump other_info

- other_info/login
  - Content: login policy or login records.
  - Use: login policy/lockout diagnosis.
- other_info/sshd
  - Content: SSH configuration or status.
  - Use: SSH connection failures due to config.
- other_info/remotelog.conf
  - Content: remote syslog configuration.
  - Use: remote log upload failures.
- other_info/command_records/*/ash_history
  - Content: per-user shell command history.
  - Use: audit manual changes or suspicious actions.

## OSDump

- systemcom.* / uart*com.*
  - Content: serial console logs for host OS or boot stage.
  - Use: OS boot failures, kernel panic, BMC boot issues.

## Notes

- Many logs are rotated: *.log.1.gz, *.log.2.gz, etc.
- When a file is missing or unknown, query NotebookLM and append here.
