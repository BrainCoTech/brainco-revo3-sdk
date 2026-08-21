"""Offline mock of the Revo3 2.x Touch domain API."""

import asyncio
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from common_init import logger, sdk


MX_TOUCH_POINT_COUNTS = [53, 56, 22, 21, 27, 21, 27, 21, 27, 21, 27]


def mx_layout_id(module_id: int) -> str:
    point_count = MX_TOUCH_POINT_COUNTS[module_id]
    if module_id == 0:
        return f"mx_palm_{point_count}"
    region = "fingertip" if module_id % 2 == 1 else "fingerpad"
    return f"mx_{region}_{point_count}"


@dataclass
class MockTouchModuleData:
    region: object
    region_index: int
    module_id: int
    layout_id: str
    sample_state: object
    points: object
    force3d: object = None
    torque2d: object = None
    resultant_force_mn: object = None
    module_status: object = None
    sensor_status: object = None


@dataclass
class MockTouchFrame:
    sequence: int
    timestamp: object
    modules: list[MockTouchModuleData]


@dataclass
class MockTouchRegionLayout:
    region: object
    module_ids: list[int]


@dataclass
class MockTouchModuleLayout:
    module_id: int
    region: object
    region_index: int
    signals: list[object]
    point_count: int
    layout_id: str


@dataclass
class MockTouchLayout:
    regions: list[MockTouchRegionLayout]
    modules: list[MockTouchModuleLayout]


class MockTouch:
    def __init__(self):
        self._enabled_mask = 0x07FF
        self._modes = [2] * 11
        self._tare = [1] * 11
        self._serial_numbers = [f"MX-MOCK-{index:02d}" for index in range(11)]
        self._sequence = 0

    @property
    def layout(self):
        return MockTouchLayout(
            regions=[
                MockTouchRegionLayout(sdk.TouchRegion.Palm, [0]),
                MockTouchRegionLayout(sdk.TouchRegion.Fingertip, [1, 3, 5, 7, 9]),
                MockTouchRegionLayout(sdk.TouchRegion.FingerPad, [2, 4, 6, 8, 10]),
            ],
            modules=[
                MockTouchModuleLayout(
                    module_id=index,
                    region=sdk.TouchRegion.Palm if index == 0 else (
                        sdk.TouchRegion.Fingertip if index % 2 == 1 else sdk.TouchRegion.FingerPad
                    ),
                    region_index=0 if index == 0 else (index // 2 if index % 2 == 1 else index // 2 - 1),
                    signals=[sdk.TouchSignal.TouchPoint],
                    point_count=MX_TOUCH_POINT_COUNTS[index],
                    layout_id=mx_layout_id(index),
                )
                for index in range(11)
            ],
        )

    async def enabled_mask(self):
        return self._enabled_mask

    async def set_enabled_mask(self, mask):
        self._enabled_mask = int(mask)

    async def set_module_enabled(self, module_index, enabled):
        bit = 1 << module_index
        self._enabled_mask = self._enabled_mask | bit if enabled else self._enabled_mask & ~bit

    async def tare(self, module_index=None):
        indexes = range(11) if module_index is None else (module_index,)
        for index in indexes:
            self._tare[index] = 1

    async def cancel_tare(self, module_index=None):
        indexes = range(11) if module_index is None else (module_index,)
        for index in indexes:
            self._tare[index] = 0

    async def tare_status(self, module_index=None):
        return self._tare[0] if module_index is None else self._tare[module_index]

    async def set_value_mode(self, mode, module_index=None):
        indexes = range(11) if module_index is None else (module_index,)
        for index in indexes:
            self._modes[index] = int(mode)

    async def value_mode(self, module_index=None):
        return self._modes[0 if module_index is None else module_index]

    async def point_counts(self):
        return MX_TOUCH_POINT_COUNTS.copy()

    async def restart(self, module_index=None):
        return None

    async def snapshot(self):
        self._sequence += 1
        modules = [
            MockTouchModuleData(
                region=sdk.TouchRegion.Palm if index == 0 else (
                    sdk.TouchRegion.Fingertip if index % 2 == 1 else sdk.TouchRegion.FingerPad
                ),
                region_index=0 if index == 0 else (index // 2 if index % 2 == 1 else index // 2 - 1),
                module_id=index,
                layout_id=mx_layout_id(index),
                sample_state=sdk.TouchSampleState.Valid,
                points=[0] * MX_TOUCH_POINT_COUNTS[index],
            )
            for index in range(11)
        ]
        return MockTouchFrame(
            sequence=self._sequence,
            timestamp=None,
            modules=modules,
        )
async def run_mock_test():
    touch = MockTouch()
    await touch.restart(1)
    await touch.restart()
    logger.info("Touch point counts: %s", await touch.point_counts())

    await touch.set_module_enabled(2, False)
    assert await touch.enabled_mask() == 0x07FB
    await touch.set_enabled_mask(0x07FF)

    await touch.tare(1)
    assert await touch.tare_status(1) == 1
    await touch.cancel_tare(1)
    await touch.tare()

    layout = touch.layout
    assert len(layout.modules) == 11
    assert layout.regions[1].module_ids == [1, 3, 5, 7, 9]
    assert layout.modules[0].signals == [sdk.TouchSignal.TouchPoint]

    await touch.set_value_mode(0)
    adc_frame = await touch.snapshot()
    assert adc_frame.modules[0].region == sdk.TouchRegion.Palm
    assert len(adc_frame.modules) == 11
    assert [len(module.points) for module in adc_frame.modules] == MX_TOUCH_POINT_COUNTS

    await touch.set_value_mode(2)
    assert await touch.value_mode(1) == 2
    force_frame = await touch.snapshot()
    assert [len(module.points) for module in force_frame.modules] == MX_TOUCH_POINT_COUNTS
    logger.info("Mock Touch 2.x test completed successfully")


if __name__ == "__main__":
    asyncio.run(run_mock_test())
