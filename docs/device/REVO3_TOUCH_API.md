# Revo3 Integrated Touch Protocol Reference

This internal protocol reference covers tactile modules that are integrated with the hand
controller and readable through the SDK's Modbus/CANFD transport. Depending on
the installed mapping, the integrated path contains 11 modules distributed
across the hand or five force/torque fingertip modules.

The integrated transport supports three tactile code families:

- `mt_*`: piezoresistive tactile array modules using 4000-series control registers and input-register data.
- `mx_*`: high-density matrix tactile modules using 5000-series holding registers.
- `hp_*`: fingertip modules providing 3D force, 2D torque, and resultant force through 6500-series control registers and input-register data; selected layouts also provide a point array.

Revo3 Ultra VisionTouch is different. The two VisionTouch supplier
implementations currently under evaluation are fingertip sensors accessed
through their own vendor SDK and a separate USB or serial connection. Their
images and derived tactile data do not pass through the hand's Modbus/CANFD
registers and are not returned by `hand.touch`. Applications must own the
vendor-channel lifecycle and align its timestamps with hand state themselves.
Some hands also contain `mt_*` or `mx_*` finger-pad and palm arrays on the main
link. After read-only metadata detection resolves that array family,
`hand.touch` returns only the five finger-pad modules and one palm module. It
does not fabricate or merge fingertip samples. The SDK must not infer this
sparse layout from the product model alone.

When an integrated register mapping cannot be identified, the SDK treats it as
unavailable instead of guessing a data shape. The
`Revo3UltraVisionTouch` model identifies the hand product only; it does not
claim that vendor tactile data is available through this API.

The low-level decoders distinguish the supported integrated code families
internally. The Manager object API normalizes them into `TouchLayout` plus a
common `TouchFrame` snapshot. `TouchLayout.regions` groups module IDs by
anatomical region, and `TouchLayout.modules` describes each module's signals,
point count, and layout ID. Applications derive counts from `modules` and each
region's `module_ids`. `TouchFrame.sequence` records frame order and
`TouchFrame.modules` holds per-module data. Unknown mappings fail closed.

## Touch Modules and Arrays

The hand has 11 physical tactile modules. The module order is shared by `mt_*` and `mx_*` touch devices.

| Module Index | Location | `mt_*` Array Address | `mt_*` Points | `mx_*` Array Address | `mx_*` Capacity | Example `mx_*` Reported Count |
|:---:|----------|:---:|:---:|:---:|:---:|:---:|
| 0 | Palm | `4200` | 36 | `5240` | 200 | 53 |
| 1 | Thumb Tip | `4250` | 31 | `5340` | 80 | 56 |
| 2 | Thumb Pad | `4290` | 57 | `5380` | 120 | 22 |
| 3 | Index Tip | `4350` | 21 | `5440` | 80 | 21 |
| 4 | Index Pad | `4400` | 52 | `5480` | 120 | 27 |
| 5 | Middle Tip | `4460` | 21 | `5540` | 80 | 21 |
| 6 | Middle Pad | `4500` | 52 | `5580` | 120 | 27 |
| 7 | Ring Tip | `4560` | 21 | `5640` | 80 | 21 |
| 8 | Ring Pad | `4600` | 52 | `5680` | 120 | 27 |
| 9 | Pinky Tip | `4660` | 21 | `5740` | 80 | 21 |
| 10| Pinky Pad | `4700` | 52 | `5780` | 120 | 27 |

## `layout_id` Mapping Table

The SDK maps tactile code families to standardized `layout_id` strings and signal capabilities:

| `module_id` | Location | `layout_id` | Point Count | Signals |
|:---:|:---|:---|:---:|:---|
| 0 | Palm | `mt_palm_36` | 36 | `[TouchPoint]` |
| 1 | Thumb Tip | `mt_thumbtip_31` | 31 | `[TouchPoint]` |
| 2 | Thumb Pad | `mt_thumbpad_57` | 57 | `[TouchPoint]` |
| 3, 5, 7, 9 | Fingertips | `mt_fingertip_21` | 21 | `[TouchPoint]` |
| 4, 6, 8, 10 | Fingerpads | `mt_fingerpad_52` | 52 | `[TouchPoint]` |
| 0 | Palm | `mx_palm_<actual_count>`; observed: `mx_palm_53` | Runtime | `[TouchPoint]` |
| 1 | Thumb Tip | `mx_fingertip_<actual_count>`; observed: `mx_fingertip_56` | Runtime | `[TouchPoint]` |
| 3, 5, 7, 9 | Fingertips | `mx_fingertip_<actual_count>`; observed: `mx_fingertip_21` | Runtime | `[TouchPoint]` |
| 2 | Thumb Pad | `mx_fingerpad_<actual_count>`; observed: `mx_fingerpad_22` | Runtime | `[TouchPoint]` |
| 4, 6, 8, 10 | Fingerpads | `mx_fingerpad_<actual_count>`; observed: `mx_fingerpad_27` | Runtime | `[TouchPoint]` |
| 0~4 | Fingertips (Thumb~Pinky) | `hp_fingertip_48` | 48 | `[TouchPoint, Force3D, Torque2D, ResultantForce]` |
| 0~4 | Fingertips (Thumb~Pinky) | `hp_fingertip_ft` | 0 | `[Force3D, Torque2D, ResultantForce]` |
| 1, 3, 5, 7, 9 (hybrid) | Fingertips (Thumb~Pinky) | `hp_fingertip_48` or `hp_fingertip_ft` | 48 or 0 | Layout-dependent `hp_*` signals shown above |
| 2 (`hp+mt`) | Thumb Pad | `mt_thumbpad_57` | 57 | `[TouchPoint]` |
| 4, 6, 8, 10 (`hp+mt`) | Fingerpads (Index~Pinky) | `mt_fingerpad_52` | 52 | `[TouchPoint]` |
| 0 (`hp+mt`) | Palm | `mt_palm_36` | 36 | `[TouchPoint]` |

Known four-character hand SN product codes select these layouts before register probing:

| Product Code | Touch Profile |
|---|---|
| `UTL1` / `UTR1` | Uniform `mt_*` array |
| `UTL2` / `UTR2` | Uniform `mx_*` array |
| `UFL1` / `UFR1` | `hp_fingertip_ft` only |
| `UFL2` / `UFR2` | `hp_fingertip_ft` + `mt_*` fingerpads/palm |
| `UFL3` / `UFR3` | `hp_fingertip_48` + `mt_*` fingerpads/palm |
| `UVL1` / `UVR1`, `UVL2` / `UVR2` | Main-link `mt_*` fingerpads/palm |
| `UVL3` / `UVR3`, `UVL4` / `UVR4` | Main-link `mx_*` fingerpads/palm |

The exact product code is authoritative because older firmware may expose stale or default values in
registers 135 and 136. Legacy and unknown variants continue to use register and read-only metadata
probing. Vision-tactile fingertips remain on their independent channel and are not part of the
main-link profile.

High-density matrix (`mx_*`) point counts are read through input-register function code `0x04`
at addresses `5191~5201`. Capacity is only the maximum register span and must not be used as the
module's point count or embedded in `layout_id`. The SDK generates the base ID from the reported
count. The example reported counts in the table are observations from one validated layout, not fixed
protocol values or compatibility guarantees. Applications must always use the count reported by the
connected device. If two hardware layouts have the same count but different point order or geometry, a controlled
layout mapping may assign a suffix such as `_v2`; the suffix must come from hardware revision or module
identity evidence and must never be inferred from point count alone. Mixed topologies use sparse
public module IDs aligned with the protocol physical IDs: module 0 for the palm, odd IDs 1/3/5/7/9
for `hp_*` fingertips (Thumb~Pinky), and even IDs 2/4/6/8/10 for fingerpads (Thumb~Pinky). For SNs without a known four-character product code, register 135 values `0x8113`,
`0x8223`, and `0x8123` select `mt_*`/`mx_*` independently for the fingerpad and palm regions; legacy
value 11 aliases `0x8113`. Legacy VisionTouch variants are detected by the `UVL/UVR` serial-number prefix and read-only array metadata. The `xs_*`
and `vts_*` technical identities are detection hints for fingertip visual-tactile channels, not stable
public numeric protocol IDs. Neither visual-tactile fingertip channel is
exposed through the main-link `TouchFrame` API. A detected VisionTouch main-link
array layout uses only public module IDs 0/2/4/6/8/10.


## `mt_*` Piezoresistive Array Registers

| Address | Description | Note |
|---------|-------------|------|
| `4000~4010` | Touch Module Enable | 11 registers (one per module). `0` = Disable, `1` = Enable. |
| `4011` | Calibrate Touch Zero (All) | Write any non-zero value to calibrate zero drift baseline. |
| `4012~4022` | Calibrate Touch Zero (Single) | 11 registers. Write `1` to calibrate a specific module. |
| `4023` | Touch Read Data Type | `mt_*` only. `0` = point-array data whose value type is selected by `4024`; `1` = compatibility-only secondary-calibrated regional force summary. `mx_*` uses `output_mode` instead. |
| `4024` | Touch Module Value Type | `0` = ADC value, `1` = unused, `2` = force value. The public API exposes only values `0` and `2`. |
| `4025` | Regional Force Tare (All) | Write `2` to clear, `3` to restore factory settings. |
| `4026~4036` | Regional Force Tare (Single) | 11 registers. Write `2` to clear, `3` to restore factory settings. |

Register `4024` value `1` is unused and is not part of the public `TouchValueMode` enum. Callers
must use `Adc` (0) or `Force` (2). Secondary-calibrated regional force values belong to read mode
`4023 = 1`, not value mode `4024`.

## Data Registers (Input, RO)

| Address | Length | Description |
|---------|--------|-------------|
| `4100~4141` | 42 | **Regional resultant force**: one value per calibrated region. Each value is the sum of all calibrated pressure points in that region. The SDK decodes each slice into the corresponding `TouchFrame.modules[*].regional_forces_mn`. |
| `4200~4751` | - | **Array Buffers**: The dense sensor matrices for each module. Refer to the mapping table above. |

## `mx_*` Registers

| Address | Length | Access | Description |
|---------|--------|--------|-------------|
| `5003~5178` | 176 | Input, RO | Module serial numbers. Each module uses 16 registers, 32 bytes, with the high byte first. |
| `5179` | 1 | Holding, WO | Restart all `mx_*` modules. Write `1`. |
| `5180~5190` | 11 | Holding, WO | Restart one `mx_*` module. Write `1`. |
| `5191~5201` | 11 | Input, RO | Mode-independent point counts. |
| `5202` | 1 | Holding, RW | Output mode for all modules. `0` = ADC value, `1` = force. |
| `5203~5213` | 11 | Holding, RW | Output mode for one module. |
| `5214` | 1 | Holding, WO | Tare command for all modules. `1` = tare, `2` = cancel. |
| `5215~5225` | 11 | Holding, WO | Tare command for one module. |
| `5226` | 1 | Holding, RO | Global tare status. `0` = not tared, `1` = tared, `2` = busy or failed. |
| `5227~5237` | 11 | Holding, RO | Tare status for one module. |
| `5240~5839` | 600 | Input, RO | Packed `mx_*` touch data. In both modes, each register carries two `uint8` points, high byte first. Module blocks use their protocol-defined maximum spans. |
| `5900~5910` | 11 | Holding, RW | Module enable/disable control. `0` = Disable, `1` = Enable. |

Output mode `0` returns one `uint8` ADC value per point in the range `0~255`. Output mode `1`
packs one `uint8` force value per point with a scale of `10 mN`. The SDK converts each force-mode
point to mN before returning it, so the public value is `raw * 10`. Module output length is
determined by input registers `5191~5201`; `200/80/120` are capacities, not fixed active point
counts.

Current `mx_*` firmware maps serial numbers, point counts, and packed tactile data to Modbus input
registers and reads them with function code `0x04`. During the compatibility period, the SDK probes
the point-count range once per connection and falls back to the legacy holding-register (`0x03`)
mapping when only that mapping returns valid counts. The selected mapping is cached for the connection;
conflicting valid responses fail closed instead of silently selecting one.

## `hp_*` Registers

The five modules are ordered Thumb Tip, Index Tip, Middle Tip, Ring Tip, and Pinky Tip. Every module retains a 38-register address slot. `hp_fingertip_48` reads all 38 registers; `hp_fingertip_ft` reads the first 14 registers in each slot.

| Address | Length | Access | Description |
|---------|--------|--------|-------------|
| `6500~6504` | 5 | RW | Module enable/disable control. `0` = Disable, `1` = Enable. |
| `6510~6514` | 5 | WO | Force/torque zeroing. Write `1` for one module. |
| `6520~6709` | 190 | RO | Five fixed 38-register address slots; each read uses 38 or 14 registers according to the detected layout. |

Within each module block, offsets 0 and 1 contain module status and sensor status. Offsets 2 through 11 contain five big-endian-word-order `float32` values in `Fx`, `Fy`, `Fz`, `Mx`, `My` order. The protocol carries `Fx`, `Fy`, and `Fz` in N; the SDK converts them to mN before exposing them in the `hp_*` module-local coordinate system. `Mx` and `My` are expressed in Nm around the local x and y axes. Their positive directions follow the module coordinate-system arrows and right-hand-rule torque directions shown in the hardware drawing.

Offsets 12 and 13 contain `Fn`, exposed as `resultant_force_mn`. It is the calibrated scalar resultant force over the entire tactile area of the module, in mN; it is not the local z-axis component and must not be interpreted as `Fz`. In `hp_fingertip_48`, offsets 14 through 37 contain 48 raw `uint8` points, with the odd-numbered point in the high byte and the even-numbered point in the low byte. `hp_fingertip_ft` does not expose these offsets; its public `point_count` is 0 and `points` is `None`.

For SNs without a known four-character product code, the SDK first uses touch type register 136 to distinguish the two layouts. If older firmware does not provide an unambiguous value, the SDK probes the first module with a 38-register input read. It retries with 14 registers only after an explicit Modbus `Illegal Data Address` response. A timeout or other transport error does not change the layout. This fallback applies equally to Modbus RTU and the CANFD register transport.

`hp_*` module status maps to `TouchSampleState`: `0` is `WarmingUp`, `1` with a normal sensor is `Valid`, and `2` or an unknown module status is `Unavailable`. A nonzero sensor status on a ready module is `SensorFault`. Force, torque, resultant-force, and point data are only published when the state is `Valid`. Applications use `TouchModuleData.sample_state` as the normalized state. Optional `TouchModuleData.diagnostics` preserves the raw values as `module_status_raw` and `sensor_fault_code_raw` for troubleshooting.

## Public API Organization

The public Touch API is organized by responsibility:

1. **Read and subscribe**: `layout`, `snapshot()`, `subscribe()`.
2. **Layout configuration**: `set_layout(layout)`.
3. **Module enable state**: `set_module_enabled()`, `module_enabled()`, `set_enabled_mask()`, `enabled_mask()`.
4. **Read mode**: `set_read_mode()`, `read_mode()` for `mt_*`.
5. **Value mode**: `set_value_mode()`, `value_mode()` for `mt_*` and `mx_*`.
6. **Zero calibration**: `tare()`, `cancel_tare()`, `tare_status()`.
7. **Module information and maintenance**: `point_counts()`, `restart()`, and `hand.device_info.touch_serial_numbers`.

For public SDK callers, prefer `hand.touch.tare()` or `hand.touch.tare(module_index)` as the unified zero-offset entry point. The SDK routes that call to the current tactile code family automatically:

- `mt_*`: global or per-module zero drift registers.
- `mx_*`: module tare commands and tare status registers.
- `hp_*`: module force/torque zeroing commands at `6510~6514`; the protocol does not define a cancel or zero-status register for these modules.

Configuration and maintenance methods are exposed directly through `hand.touch`. The SDK routes supported operations by the current layout and returns `UnsupportedCapability` before sending a command when the active touch protocol does not provide the requested operation.

`set_layout(layout)` accepts confirmed integrated layouts on Revo3 Ultra Touch.
On Revo3 Ultra VisionTouch it accepts only the main-link `mt_*` or `mx_*`
finger-pad and palm modules (physical module IDs 0/2/4/6/8/10); independent
vision tactile fingertips remain outside `TouchLayout` and `TouchFrame`. If the
serial number cannot identify the product, callers must also provide an
UltraVisionTouch model override while connecting. Both overrides are scoped to
the current SDK session and do not write device registers.

## Python SDK Examples

The following snippets illustrate operations on an already connected `hand`. Connection lifecycle, timeout handling, and structured error recovery are omitted here; production code must follow [`REVO3_API.zh-CN.md`](../api/REVO3_API.zh-CN.md).

```python
frame = await hand.touch.snapshot()
selected = await hand.touch.snapshot(module_indices=[0, 2, 4])
palm = await hand.touch.module_snapshot(0)
for module in frame.modules:
    print(module.region, module.module_id, len(module.points or []))
    if module.force3d is not None:
        print(module.force3d.z, module.resultant_force_mn)  # mN
```

```python
# 1. Module Management
await hand.touch.set_enabled_mask(0x07FF)  # Enable all 11 modules
enabled_mask = await hand.touch.enabled_mask()

# 2. Zero calibration
await hand.touch.tare()  # Calibrate zero drift for all modules
# await hand.touch.tare(module_index)  # Or calibrate a specific module

# Tactile configuration
await hand.touch.set_read_mode(sdk.TouchReadMode.PointArray)
await hand.touch.set_value_mode(sdk.TouchValueMode.Force)

# 3. Read Summary Force (42 values mapped by the active layout)
layout = hand.touch.layout
if layout is None:
    raise RuntimeError("Touch layout is unavailable")
# Compatibility-only secondary-calibrated summary mode; do not use in new applications.
await hand.touch.set_read_mode(sdk.TouchReadMode.LegacyForceSummary)
summary_frame = await hand.touch.snapshot()
for module in summary_frame.modules:
    if module.regional_forces_mn is not None:
        print(module.region, module.region_index, module.regional_forces_mn)

# 4. Read Dense Array Data in a separate mode and frame
await hand.touch.set_read_mode(sdk.TouchReadMode.PointArray)
points_frame = await hand.touch.snapshot()
thumb_pad_layout = next(
    module
    for module in layout.modules
    if module.region == sdk.TouchRegion.FingerPad and module.region_index == 0
)
# Match by module_id; the modules array position equals module_id only in pure mt_*/mx_* layouts.
thumb_pad_data = next(
    module.points
    for module in points_frame.modules
    if module.module_id == thumb_pad_layout.module_id
)
```

`LegacyForceSummary` is the `4023 = 1` secondary-calibrated regional-force mode
for a small number of shipped devices. It remains a compatibility-only API until a removal version
and migration requirement are recorded in the 2.0 Open Items and Decision Register; this document
does not define a removal release. New applications should not depend on it. `LegacyForceSummary`
and `PointArray` are mutually exclusive for
`mt_*`. The two frames above may use different sampling paths or algorithms and are not one atomic
physical sample. Do not present them as a simultaneous "summary + arrays" read.

## `mx_*` Python Examples

```python
layout = hand.touch.layout
if layout and any(module.layout_id.startswith("mx_") for module in layout.modules):
    info = await hand.refresh_device_info()
    sns = info.touch_serial_numbers if info is not None else []
    counts = await hand.touch.point_counts()

    await hand.touch.set_value_mode(sdk.TouchValueMode.Force)
    mode = await hand.touch.value_mode()

    await hand.touch.tare()
    status = await hand.touch.tare_status()

    frame = await hand.touch.snapshot()
    palm_data = frame.modules[0].points  # Length equals layout.modules[0].point_count.
    all_touch = frame.modules
```

`snapshot(module_indices=[...])` reads only the selected enabled modules and
returns them in request order. `module_snapshot(module_index)` is the
single-module form. The selection uses public module IDs from `TouchLayout` and
does not change `enabled_mask`. Empty selections, duplicate IDs, and IDs absent
from the current layout fail before tactile data reads. In `PointArray` mode,
each selected enabled `mt_*` module requires one data RTT. A hybrid layout with
five `mt_*` fingerpads and one `mt_*` palm therefore uses 1–6 point-array data
RTTs instead of always using six; enable-state and uncached mode queries are
additional control RTTs. `LegacyForceSummary` uses one shared summary data RTT.
