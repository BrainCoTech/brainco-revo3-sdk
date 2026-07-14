# Revo3 Touch API Reference

Revo3 tactile sensors provide high-resolution force feedback through 11 physical modules distributed across the hand.

The SDK supports two Revo3 tactile register mappings through `TouchVendor`:

- `TouchVendor::Pressure`: legacy pressure tactile mapping using 4000-series control registers and input-register data.
- `TouchVendor::Matrix`: matrix tactile mapping using 5003-series holding registers.

VisionTouch is not a `TouchVendor` value. It is identified by the hardware type `Revo3UltraVisionTouch` (SN prefixes `UVL/UVR`) and may coexist with Pressure or Matrix tactile modules on the same hand. Use `get_device_info().hardware_type` to decide whether VisionTouch tools are available, and use `get_touch_vendor()` only to select the Pressure or Matrix tactile register mapping.

When `get_touch_vendor()` returns `Unknown`, the SDK treats normal tactile Pressure/Matrix modules as unavailable. A `Revo3UltraVisionTouch` device keeps its VisionTouch hardware type even when the tactile vendor is `Unknown`.

## Touch Modules and Arrays

The hand has 11 physical tactile modules. The module order is shared by Pressure and Matrix touch devices.

| Module Index | Location | Pressure Touch Array Address | Pressure Touch Points | Matrix Array Address | Matrix Points |
|:---:|----------|:---:|:---:|
| 0 | Palm | `4200` | 36 | `5240` | 60 |
| 1 | Thumb Tip | `4250` | 31 | `5300` | 60 |
| 2 | Thumb Pad | `4290` | 57 | `5360` | 60 |
| 3 | Index Tip | `4350` | 21 | `5420` | 60 |
| 4 | Index Pad | `4400` | 52 | `5480` | 60 |
| 5 | Middle Tip | `4460` | 21 | `5540` | 60 |
| 6 | Middle Pad | `4500` | 52 | `5600` | 60 |
| 7 | Ring Tip | `4560` | 21 | `5660` | 60 |
| 8 | Ring Pad | `4600` | 52 | `5720` | 60 |
| 9 | Pinky Tip | `4660` | 21 | `5780` | 60 |
| 10| Pinky Pad | `4700` | 52 | `5840` | 60 |

## Pressure Touch Registers

| Address | Description | Note |
|---------|-------------|------|
| `4000~4010` | Touch Module Enable | 11 registers (one per module). `0` = Disable, `1` = Enable. |
| `4011` | Calibrate Touch Zero (All) | Write any non-zero value to calibrate zero drift baseline. |
| `4012~4022` | Calibrate Touch Zero (Single) | 11 registers. Write `1` to calibrate a specific module. |
| `4023` | Touch Read Data Type | `0` = Tactile Array, `1` = Force Summary. |
| `4024` | Touch Module Value Type | `0` = ADC Value, `1` = Raw Pressure, `2` = Force. |
| `4025` | Regional Force Tare (All) | Write `2` to clear, `3` to restore factory settings. |
| `4026~4036` | Regional Force Tare (Single) | 11 registers. Write `2` to clear, `3` to restore factory settings. |

## Data Registers (Input, RO)

| Address | Length | Description |
|---------|--------|-------------|
| `4100~4141` | 42 | **Summary Force**: The calculated aggregate force per pad.<br>Maps directly to 42 specific sensor zones (Palm, Thumb, Index, etc.) |
| `4200~4751` | - | **Array Buffers**: The dense sensor matrices for each module. Refer to the mapping table above. |

## Matrix Touch Registers

All Matrix touch registers are holding registers.

| Address | Length | Access | Description |
|---------|--------|--------|-------------|
| `5003~5178` | 176 | RO | Module serial numbers. Each module uses 16 registers, 32 bytes. |
| `5179` | 1 | WO | Restart all Matrix touch modules. Write `1`. |
| `5180~5190` | 11 | WO | Restart one Matrix touch module. Write `1`. |
| `5191~5201` | 11 | RO | Module point counts. |
| `5202` | 1 | RW | Output mode for all modules. `0` = ADC value, `1` = force. |
| `5203~5213` | 11 | RW | Output mode for one module. |
| `5214` | 1 | WO | Tare command for all modules. `1` = tare, `2` = cancel. |
| `5215~5225` | 11 | WO | Tare command for one module. |
| `5226` | 1 | RO | Global tare status. `0` = not tared, `1` = tared, `2` = busy or failed. |
| `5227~5237` | 11 | RO | Tare status for one module. |
| `5240~5899` | 660 | RO | Matrix touch data. 11 modules, 60 registers per module. |
| `5900~5910` | 11 | RW | Module enable/disable control. `0` = Disable, `1` = Enable. |

## Python SDK Examples

```python
# 1. Module Management
await ctx.revo3_set_all_touch_modules_enabled(slave_id, 0x07FF) # Enable all 11 modules
enabled_mask = await ctx.revo3_get_all_touch_modules_enabled(slave_id)

# 2. Calibration / Zeroing
await ctx.revo3_set_touch_data_type(slave_id, sdk.TouchDataMode.TactileArray)
await ctx.revo3_set_touch_module_value_type(slave_id, sdk.TouchModuleValueType.Force)
await ctx.revo3_calibrate_touch_zero(slave_id)  # Calibrate zero drift for all modules
# await ctx.revo3_calibrate_touch_zero_single(slave_id, module_id) # Or calibrate a specific module

# Pressure Touch explicit APIs
await ctx.revo3_calibrate_pressure_touch_zero(slave_id)  # 4011, write 1
await ctx.revo3_calibrate_pressure_touch_module_zero(slave_id, module_id)  # 4012 + module_id, write 1
await ctx.revo3_set_pressure_touch_force_tare(
    slave_id,
    sdk.PressureTouchForceTareCommand.Clear,
)  # 4025, write 2
await ctx.revo3_set_pressure_touch_force_tare(
    slave_id,
    sdk.PressureTouchForceTareCommand.RestoreFactory,
)  # 4025, write 3
await ctx.revo3_set_pressure_touch_module_force_tare(
    slave_id,
    module_id,
    sdk.PressureTouchForceTareCommand.Clear,
)  # 4026 + module_id, write 2
await ctx.revo3_set_pressure_touch_module_force_tare(
    slave_id,
    module_id,
    sdk.PressureTouchForceTareCommand.RestoreFactory,
)  # 4026 + module_id, write 3

# 3. Read Summary Force (Fast, 42 values)
summary_42 = await ctx.revo3_get_touch_summary(slave_id)
print(f"Palm Force: {summary_42[0]}")

# 4. Read Dense Array Data
# (e.g., Module 2 = Thumb Pad, returns 57 points on Pressure and 60 points on Matrix)
thumb_pad_data = await ctx.revo3_get_touch_module_data(slave_id, 2)

# 5. Bulk Read All (Summary + 11 Arrays)
all_touch = await ctx.revo3_get_all_touch_data(slave_id)
```

## Matrix Touch Python Examples

```python
vendor = await ctx.get_touch_vendor(slave_id)
if int(vendor) == 2:  # Matrix
    sns = await ctx.revo3_get_all_matrix_touch_module_serial_numbers(slave_id)
    counts = await ctx.revo3_get_all_matrix_touch_module_point_counts(slave_id)

    await ctx.revo3_set_matrix_touch_output_mode(slave_id, sdk.MatrixTouchOutputMode.Force)
    mode = await ctx.revo3_get_matrix_touch_output_mode(slave_id)

    await ctx.revo3_set_matrix_touch_tare(slave_id, sdk.MatrixTouchTareCommand.Tare)
    status = await ctx.revo3_get_matrix_touch_tare_status(slave_id)

    palm_data = await ctx.revo3_get_touch_module_data(slave_id, 0)  # 60 values on Matrix
    all_touch = await ctx.revo3_get_all_touch_data(slave_id)
```
