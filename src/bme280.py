"""Minimal BME280 driver for Raspberry Pi (I2C)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

try:
    from smbus2 import SMBus
except ImportError:  # pragma: no cover - optional dependency
    SMBus = None  # type: ignore


@dataclass
class CalibrationData:
    dig_T1: int
    dig_T2: int
    dig_T3: int
    dig_P1: int
    dig_P2: int
    dig_P3: int
    dig_P4: int
    dig_P5: int
    dig_P6: int
    dig_P7: int
    dig_P8: int
    dig_P9: int
    dig_H1: int
    dig_H2: int
    dig_H3: int
    dig_H4: int
    dig_H5: int
    dig_H6: int


class BME280:
    """Simple BME280 reader using smbus2."""

    REG_ID = 0xD0
    REG_RESET = 0xE0
    REG_CTRL_HUM = 0xF2
    REG_CTRL_MEAS = 0xF4
    REG_CONFIG = 0xF5
    REG_PRESS_MSB = 0xF7

    CHIP_ID = 0x60

    def __init__(self, bus_id: int = 1, address: int = 0x76) -> None:
        if SMBus is None:
            raise RuntimeError("smbus2 is required to use the BME280 driver")
        self.bus_id = bus_id
        self.address = address
        self.bus = SMBus(bus_id)
        self.calibration = self._read_calibration()
        self._configure()
        self._t_fine = 0

    def close(self) -> None:
        if self.bus is not None:
            self.bus.close()

    def _read_u8(self, register: int) -> int:
        return self.bus.read_byte_data(self.address, register)

    def _read_block(self, start: int, length: int) -> bytes:
        return bytes(self.bus.read_i2c_block_data(self.address, start, length))

    @staticmethod
    def _u16_le(data: bytes) -> int:
        return data[0] | (data[1] << 8)

    @staticmethod
    def _s16_le(data: bytes) -> int:
        value = data[0] | (data[1] << 8)
        if value & 0x8000:
            value = -((value ^ 0xFFFF) + 1)
        return value

    def _read_calibration(self) -> CalibrationData:
        chip_id = self._read_u8(self.REG_ID)
        if chip_id != self.CHIP_ID:
            raise RuntimeError(f"Unexpected BME280 chip id 0x{chip_id:02x}")

        cal1 = self._read_block(0x88, 26)
        cal2 = self._read_block(0xE1, 7)

        dig_T1 = self._u16_le(cal1[0:2])
        dig_T2 = self._s16_le(cal1[2:4])
        dig_T3 = self._s16_le(cal1[4:6])

        dig_P1 = self._u16_le(cal1[6:8])
        dig_P2 = self._s16_le(cal1[8:10])
        dig_P3 = self._s16_le(cal1[10:12])
        dig_P4 = self._s16_le(cal1[12:14])
        dig_P5 = self._s16_le(cal1[14:16])
        dig_P6 = self._s16_le(cal1[16:18])
        dig_P7 = self._s16_le(cal1[18:20])
        dig_P8 = self._s16_le(cal1[20:22])
        dig_P9 = self._s16_le(cal1[22:24])

        dig_H1 = cal1[25]
        dig_H2 = self._s16_le(cal2[0:2])
        dig_H3 = cal2[2]
        dig_H4 = (cal2[3] << 4) | (cal2[4] & 0x0F)
        if dig_H4 & 0x800:
            dig_H4 = -((dig_H4 ^ 0xFFF) + 1)
        dig_H5 = (cal2[5] << 4) | (cal2[4] >> 4)
        if dig_H5 & 0x800:
            dig_H5 = -((dig_H5 ^ 0xFFF) + 1)
        dig_H6 = cal2[6]
        if dig_H6 & 0x80:
            dig_H6 = -((dig_H6 ^ 0xFF) + 1)

        return CalibrationData(
            dig_T1=dig_T1,
            dig_T2=dig_T2,
            dig_T3=dig_T3,
            dig_P1=dig_P1,
            dig_P2=dig_P2,
            dig_P3=dig_P3,
            dig_P4=dig_P4,
            dig_P5=dig_P5,
            dig_P6=dig_P6,
            dig_P7=dig_P7,
            dig_P8=dig_P8,
            dig_P9=dig_P9,
            dig_H1=dig_H1,
            dig_H2=dig_H2,
            dig_H3=dig_H3,
            dig_H4=dig_H4,
            dig_H5=dig_H5,
            dig_H6=dig_H6,
        )

    def _configure(self) -> None:
        # humidity oversampling x1
        self.bus.write_byte_data(self.address, self.REG_CTRL_HUM, 0x01)
        # temp/pressure oversampling x1, mode normal
        self.bus.write_byte_data(self.address, self.REG_CTRL_MEAS, 0x27)
        # standby 1000ms, filter off
        self.bus.write_byte_data(self.address, self.REG_CONFIG, 0xA0)

    def read_compensated(self) -> Tuple[float, float, float]:
        data = self._read_block(self.REG_PRESS_MSB, 8)
        adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        adc_h = (data[6] << 8) | data[7]

        temperature = self._compensate_temperature(adc_t)
        pressure = self._compensate_pressure(adc_p)
        humidity = self._compensate_humidity(adc_h)
        return temperature, pressure, humidity

    def _compensate_temperature(self, adc_t: int) -> float:
        c = self.calibration
        var1 = (adc_t / 16384.0 - c.dig_T1 / 1024.0) * c.dig_T2
        var2 = ((adc_t / 131072.0 - c.dig_T1 / 8192.0) ** 2) * c.dig_T3
        self._t_fine = int(var1 + var2)
        temperature = (var1 + var2) / 5120.0
        return temperature

    def _compensate_pressure(self, adc_p: int) -> float:
        c = self.calibration
        var1 = self._t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * c.dig_P6 / 32768.0
        var2 = var2 + var1 * c.dig_P5 * 2.0
        var2 = var2 / 4.0 + c.dig_P4 * 65536.0
        var1 = (c.dig_P3 * var1 * var1 / 524288.0 + c.dig_P2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * c.dig_P1
        if var1 == 0:
            return float("nan")
        pressure = 1048576.0 - adc_p
        pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
        var1 = c.dig_P9 * pressure * pressure / 2147483648.0
        var2 = pressure * c.dig_P8 / 32768.0
        pressure = pressure + (var1 + var2 + c.dig_P7) / 16.0
        return pressure / 100.0

    def _compensate_humidity(self, adc_h: int) -> float:
        c = self.calibration
        var = self._t_fine - 76800.0
        var = (
            (adc_h - (c.dig_H4 * 64.0 + c.dig_H5 / 16384.0 * var))
            * (c.dig_H2 / 65536.0)
            * (1.0 + c.dig_H6 / 67108864.0 * var * (1.0 + c.dig_H3 / 67108864.0 * var))
        )
        var = var * (1.0 - c.dig_H1 * var / 524288.0)
        if var > 100.0:
            var = 100.0
        elif var < 0.0:
            var = 0.0
        return var
