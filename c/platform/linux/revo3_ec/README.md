# Revo3 EtherCAT Pure C++ Example

This Linux-only example controls a BrainCo Revo3 hand directly through the
IgH EtherCAT master (`libethercat`). It does not link to the Rust SDK or the
Revo3 SDK shared library.

The implementation starts from the Revo3 fixed PDO mapping and then detects the
assigned PDO layout exposed by the connected slave SII:

- RxPDO `0x1600`: 23 velocity, position, current, `Kp`, and `Kd` values
- RxPDO `0x1601`: optional extra output entries when exposed by firmware
- TxPDO `0x1A00`: 23 status, velocity, position, current, and error values
- TxPDO `0x1A01`: touch packet index, valid length, and the detected
  `0x7007` payload capacity
- SDO ranges: read-only `0x8000..0x87FF`, write-only `0x8800..0x8FFF`, and
  read/write `0x9000` and above

Non-touch protocol coverage in this C++ example is split by access pattern:

- Motor PDO control/status objects `0x6000..0x6004` and `0x7000..0x7004`
  are handled by `revo3_ethercat.cpp` and exercised by `revo3_pdo` and
  `revo3_benchmark`.
- Read-only device and motor SDOs, including `0x8001..0x8003`,
  `0x8004..0x8018`, `0x8019`, `0x801A`, and `0x801B`, are available through
  `revo3_sdo`; `revo3_benchmark` also reads the identity, motor SN, and motor
  version fields at startup.
- Non-touch write-only commands `0x8802..0x8807` and read/write parameters
  `0x9003`, `0x9004`, and `0x9006..0x900E` are available through generic
  `revo3_sdo write` and `revo3_sdo read` commands. These commands are not run
  by automated tests because they can reset, calibrate, stop, or reconfigure a
  real hand.

The current default PDO layout is defined in `revo3_ethercat.hpp` as
`default_pdo_layout()`. Keep this layout aligned with the shipped ESI XML.
Additional firmware PDO layouts can be added as new `PdoLayout` constants
without rewriting the cyclic read/write code.

## Prerequisites

Install and configure the IgH EtherCAT master, then make sure `ecrt.h` and
`libethercat.so` are available under `/usr/local` (or set
`ETHERCAT_PREFIX`). The EtherCAT service and the selected network interface
must already be configured.

This example must run on a Linux EtherCAT host. macOS can edit or cross-check
the source tree, but it cannot run the IgH kernel master or create
`/dev/EtherCAT0`.

For Ubuntu kernels in the Linux 6.x series, use the latest stable IgH 1.6.x
release or the latest `stable-1.6` branch when rebuilding kernel modules for
the active kernel. The runtime kernel shown by `uname -r` must match the
directory where the IgH modules are installed.

Minimal IgH runtime checks:

```bash
uname -r
ethercat version
find /lib/modules/$(uname -r) -name 'ec_master.ko*' -o \
  -name 'ec_generic.ko*'
sudo depmod -a
sudo systemctl daemon-reload
sudo systemctl restart ethercat
systemctl status ethercat --no-pager -l
ls -l /dev/EtherCAT*
ethercat master
ethercat slaves
```

Find the EtherCAT NIC name and MAC address first:

```bash
ip -br link
```

Then configure `/usr/local/etc/ethercat.conf` with the selected NIC name or
MAC address:

```bash
MASTER0_DEVICE="<ethercat-nic-name-or-mac>"
DEVICE_MODULES="generic"  # Correct spelling; loads ec_generic
```

Use a native NIC-specific module, such as `r8169`, `igb`, `igc`, or `e1000e`,
only if that module was built for the active kernel and the host intentionally
uses the matching network adapter driver. `DEVICE_MODULES="genric"` is a typo
and makes `ethercatctl` try to load the nonexistent `ec_genric` module.

The EtherCAT service should start and create `/dev/EtherCAT0` even before a
hand is connected. If `ethercat master` shows `Link: DOWN` or the NIC shows
`NO-CARRIER`, the master is running but the physical link is not up yet; check
the EtherCAT cable, the Revo3 EtherCAT port, and hand power before debugging
the C++ example.

To grant a regular user access to the master device, create a dedicated group
and a persistent udev rule:

```bash
sudo groupadd -f ethercat
sudo usermod -aG ethercat "$USER"
echo 'KERNEL=="EtherCAT[0-9]*", GROUP="ethercat", MODE="0660"' | \
  sudo tee /etc/udev/rules.d/99-ethercat.rules
sudo udevadm control --reload-rules
sudo systemctl restart ethercat
```

Log out and back in once after changing group membership, then verify with
`id` and `ls -l /dev/EtherCAT0`. `newgrp ethercat` only updates the current
shell and may rerun shell startup files.

## Build

```bash
make

# Non-default IgH installation prefix
make ETHERCAT_PREFIX=/opt/etherlab
```

## PDO

Monitor slave position 0 at 1 kHz:

```bash
make grant-capabilities
./revo3_pdo 0
```

Use the optional realtime scheduler and Distributed Clocks configuration when
measuring tighter cycle times:

```bash
./revo3_pdo 0 --frequency 1000 --realtime 49 --dc
```

`--dc` uses the ESI XML DC `AssignActivate` value `0x0300` by default and sets
Sync0 to the selected cycle period. Realtime mode requests `SCHED_FIFO` and
locks memory; it requires `cap_sys_nice` plus `cap_ipc_lock`, `sudo`, or an
equivalent system policy. `make grant-capabilities` applies those capabilities
to both `revo3_pdo` and `revo3_benchmark`.
The loop uses `clock_nanosleep` with absolute `CLOCK_MONOTONIC` deadlines.

The PDO program reads `0x7002:01..0x17` over SDO and initializes all target
positions before activating cyclic communication. To deliberately command
one motor, pass raw protocol values for position, `Kp`, and `Kd`:

```bash
./revo3_pdo 0 --command 6 30000 100 20
```

Run a repeated quintic MIT position plan using raw EtherCAT PDO values:

```bash
./revo3_pdo 0 --frequency 1000 --dc --realtime 49 \
  --mit-plan 6 30000 100 20 2 3
```

The arguments after `--mit-plan` are `joint`, raw target position, raw `Kp`,
raw `Kd`, seconds per segment, and round-trip repeat count. The plan starts at
the position read during initialization, moves to the target and back with
zero endpoint velocity, reads feedback every PDO cycle, and prints the selected
joint once per second. It briefly holds the returned start position and clears
the joint gains when the plan completes or is interrupted.

Run the same kind of plan for the full hand first, then each representative
finger joint sequentially:

```bash
./revo3_pdo 0 --no-touch-pdo --mit-plan-all
```

With no values, `--mit-plan-all` uses the same defaults as the Modbus MIT plan
example: 100 Hz, target 80.00 deg, `Kp` 3.00, `Kd` 0.30, 0.8 seconds per
segment, and one round trip per group. Raw values can still be supplied:

```bash
./revo3_pdo 0 --frequency 100 --no-touch-pdo \
  --mit-plan-all 3000 100 20 2 1
```

The optional arguments after `--mit-plan-all` are raw target position, raw
`Kp`, raw `Kd`, seconds per segment, and round-trip repeat count per group. The
demo runs `J1,J5,J9,J13,J16,J20` together, then `J1`, `J5`, `J9`, `J13`, `J16`,
and `J20` one group at a time, then repeats from the full hand until
interrupted.

Motor indices accepted by the demo are `0..20`. The fixed EtherCAT PDO has
23 channels; channels 21 and 22 remain available through `MotorCommand` for
future firmware use.

After activation the program waits for the slave to reach OP state before
entering the main loop. If OP is not reached, the error message includes link,
responding-slave, master AL, and slave AL diagnostics.

If the slave stays in PREOP, collect the kernel transition log:

```bash
sudo dmesg -C
./revo3_pdo 0 --frequency 100 --op-timeout 9000 --no-touch-pdo
sudo dmesg | tail -120
```

`--no-touch-pdo` is a diagnostic mode that configures only motor TxPDO
`0x1A00` on SM3. If motor-only mode reaches OP but default mode does not,
the touch TxPDO `0x1A01` or the device touch capability is the likely cause.
If both modes stay in PREOP and the kernel log contains
`Failed to determine PDO sync manager for FMMU` or AL status `0x001E`
(`Invalid input configuration`), the connected slave is not exposing the
process-data sync manager information that IgH needs from SII/EEPROM. The ESI
SM2 Outputs at `0x1100` and SM3 Inputs at `0x1400`; the same information must
be present in the slave SII/EEPROM or provided by firmware. IgH's public
user-space API configures PDO assignment and mapping, but it does not provide
an API to override SM physical start addresses and default sizes from an
application.

For the full-touch default PDO, verify that the master can read the complete
SII:

```bash
ethercat xml -p 0
ethercat pdos -p 0
```

Expected full-touch SII/PDO information includes SM2 `DefaultSize=230`, SM3
`DefaultSize=680`, and TxPDO `0x1A01` with touch packet metadata plus the
`0x7007:01..0x7007:C8` payload entries. Upstream IgH `stable-1.6` and
`stable-1.7` define `EC_MAX_SII_SIZE` as 4096 words in `master/globals.h` to
avoid unbounded SII scans. If the Revo3 SII is larger than that limit, an
unpatched master can stop before the touch PDO category and fail to expose
SM3/`0x1A01` completely. Raising the local IgH limit, for example to 16384
words, can make this host read the complete SII and enter OP, but that is a
host-side patch. For firmware intended for customers or other EtherCAT
masters, prefer a smaller default SII/PDO layout or confirm that the target
master accepts the full SII size.

## SDO

```bash
# Read common device information
./revo3_sdo 0 info

# Read the hand type (0x801B:00)
./revo3_sdo 0 read 0x801B 0 u16

# Read motor system voltage (0x801A:03)
./revo3_sdo 0 read 0x801A 3 u16

# Read motor 1 protect current (0x900A:01)
./revo3_sdo 0 read 0x900A 1 u16

# Enable the buzzer (0x9003:00)
./revo3_sdo 0 write 0x9003 0 u16 1

# Clear motor error (0x8806:00)
./revo3_sdo 0 write 0x8806 0 u16 1

# Send the software reset command (0x8804:00)
./revo3_sdo 0 write 0x8804 0 u16 1
```

SDO writes take effect on real hardware. Verify the object index, access
permission, and value before running a write command.

## Benchmark

Run one benchmark scenario directly:

```bash
./revo3_benchmark --scenario motor --read full-state --control none \
  --duration 10 --slave-position 0 --frequency 1000
```

For DC/realtime timing tests:

```bash
./revo3_benchmark --scenario motor --read full-state --control none \
  --duration 10 --slave-position 0 --frequency 1000 --realtime 49 --dc
```

Extra DC diagnostics are available when investigating OP transition failures:

```bash
./revo3_benchmark --scenario motor --read full-state --control none \
  --duration 3 --slave-position 0 --frequency 200 --op-timeout 9000 \
  --dc --dc-assign 0x0300 --sync0-shift-ns 0 \
  --sync1-cycle-ns 0 --sync1-shift-ns 0 --op-warmup-ms 1000 \
  --no-touch-pdo
```

`--dc-assign`, `--sync0-shift-ns`, `--sync1-cycle-ns`,
`--sync1-shift-ns`, and `--op-warmup-ms` are diagnostic options. Keep DC
disabled for formal benchmark entries unless the target frequency reaches OP
and completes the run consistently.

