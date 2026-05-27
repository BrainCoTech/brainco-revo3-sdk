# Revo3 Touch API Reference

Revo3 Tactile Array sensors provide high-resolution force feedback through 11 physical modules distributed across the hand.

> **Note:** All APIs use the Revo3 protocol with the **4000-series** touch register mapping.

## Touch Modules and Arrays

The hand has 11 physical tactile modules. The Modbus protocol maps these to 26 "Summary" force values (legacy alignment) and 11 dense array buffers.

| Module Index | Location | Array Address | Active Points |
|:---:|----------|:---:|:---:|
| 0 | Palm | `4200` | 36 |
| 1 | Thumb Tip | `4250` | 31 |
| 2 | Thumb Pad | `4290` | 57 |
| 3 | Index Tip | `4350` | 21 |
| 4 | Index Pad | `4400` | 52 |
| 5 | Middle Tip | `4450` | 21 |
| 6 | Middle Pad | `4500` | 52 |
| 7 | Ring Tip | `4550` | 21 |
| 8 | Ring Pad | `4600` | 52 |
| 9 | Pinky Tip | `4650` | 21 |
| 10| Pinky Pad | `4700` | 52 |

## Control Registers (Holding, R/W)

| Address | Description | Note |
|---------|-------------|------|
| `4000~4010` | Touch Module Enable | 11 registers (one per module). `0` = Disable, `1` = Enable. |
| `4011` | Clear All Pressure | Write any non-zero value to zero-out the baseline. |
| `4012~4022` | Clear Module Pressure | 11 registers. Write `1` to zero-out a specific module. |
| `4023` | Touch Data Type | `0` = Calibrated Pressure, `1` = Array Pressure. |

## Data Registers (Input, RO)

| Address | Length | Description |
|---------|--------|-------------|
| `4100~4125` | 26 | **Summary Force**: The calculated aggregate force per pad.<br>Maps directly to 26 specific sensor zones (Palm, Thumb T1/T2/T3, etc.) |
| `4200~4748` | - | **Array Buffers**: The dense sensor matrices for each module. Refer to the mapping table above. |

## Python SDK Examples

```python
# 1. Module Management
sdk.revo3_set_all_touch_modules_enabled(slave_id, 0x07FF) # Enable all 11 modules
enabled_mask = sdk.revo3_get_all_touch_modules_enabled(slave_id)

# 2. Calibration / Zeroing
sdk.revo3_set_touch_data_type(slave_id, 0) # 0 = Calibrated, 1 = Raw array
sdk.revo3_reset_all_touch_pressure(slave_id)

# 3. Read Summary Force (Fast, 26 values)
summary_26 = sdk.revo3_get_touch_summary(slave_id)
print(f"Palm Force: {summary_26[0]}")

# 4. Read Dense Array Data
# (e.g., Module 2 = Thumb Pad, returns 51 points)
thumb_pad_data = sdk.revo3_get_touch_module_data(slave_id, 2)

# 5. Bulk Read All (Summary + 11 Arrays)
all_touch = sdk.revo3_get_all_touch_data(slave_id)
```
