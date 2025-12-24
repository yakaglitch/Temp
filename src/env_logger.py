"""Environmental logging for BME280 with smoothing and CSV rotation."""

from __future__ import annotations

import json
import os
import signal
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Optional, Tuple

from bme280 import BME280


@dataclass
class Config:
    sample_hz: int = 50
    window_samples: int = 50
    store_interval_s: int = 60
    i2c_bus: int = 1
    i2c_address: int = 0x76
    data_dir: Path = Path("data")
    backup_dir: Path = Path("data/BU")
    live_file: Path = Path("data/live.json")
    freeze_on_error: bool = True


class MovingAverage:
    def __init__(self, window: int) -> None:
        self.window = window
        self.buffer: Deque[float] = deque(maxlen=window)
        self.sum = 0.0

    def add(self, value: float) -> None:
        if len(self.buffer) == self.window:
            self.sum -= self.buffer[0]
        self.buffer.append(value)
        self.sum += value

    def mean(self) -> Optional[float]:
        if not self.buffer:
            return None
        return self.sum / len(self.buffer)


class EnvLogger:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.keep_running = True
        self.sensor = BME280(bus_id=config.i2c_bus, address=config.i2c_address)
        self.temp_avg = MovingAverage(config.window_samples)
        self.press_avg = MovingAverage(config.window_samples)
        self.hum_avg = MovingAverage(config.window_samples)
        self.last_success_minute: Optional[int] = None
        self.last_saved_minute: Optional[int] = None

    def run(self) -> None:
        self._prepare_dirs()
        period = 1.0 / self.config.sample_hz
        next_tick = time.monotonic()

        while self.keep_running:
            next_tick += period
            self._tick()
            sleep_time = next_tick - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)

        self.sensor.close()

    def stop(self) -> None:
        self.keep_running = False

    def _prepare_dirs(self) -> None:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.backup_dir.mkdir(parents=True, exist_ok=True)

    def _tick(self) -> None:
        now = time.time()
        minute = int(now // self.config.store_interval_s)
        had_success = False

        try:
            temperature, pressure, humidity = self.sensor.read_compensated()
            self.temp_avg.add(temperature)
            self.press_avg.add(pressure)
            self.hum_avg.add(humidity)
            self.last_success_minute = minute
            had_success = True
        except Exception:
            if not self.config.freeze_on_error:
                self.temp_avg = MovingAverage(self.config.window_samples)
                self.press_avg = MovingAverage(self.config.window_samples)
                self.hum_avg = MovingAverage(self.config.window_samples)

        if had_success:
            self._write_live(now)

        if minute != self.last_saved_minute:
            self.last_saved_minute = minute
            if self.last_success_minute == minute:
                self._write_minute_row(now)

    def _write_live(self, now: float) -> None:
        payload = self._current_payload(now)
        if payload is None:
            return
        tmp_path = self.config.live_file.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp_path, self.config.live_file)

    def _current_payload(self, now: float) -> Optional[dict]:
        temperature = self.temp_avg.mean()
        pressure = self.press_avg.mean()
        humidity = self.hum_avg.mean()
        if temperature is None or pressure is None or humidity is None:
            return None
        return {
            "timestamp": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "epoch": int(now),
            "temperature_c": round(temperature, 3),
            "pressure_hpa": round(pressure, 3),
            "humidity_rh": round(humidity, 3),
        }

    def _write_minute_row(self, now: float) -> None:
        payload = self._current_payload(now)
        if payload is None:
            return

        timestamp = payload["timestamp"]
        epoch = payload["epoch"]
        row = (
            f"{timestamp},{epoch},"
            f"{payload['temperature_c']:.3f},"
            f"{payload['pressure_hpa']:.3f},"
            f"{payload['humidity_rh']:.3f}"
        )

        dt = datetime.fromtimestamp(now, tz=timezone.utc)
        year_name = f"{dt.year}.csv"
        month_name = f"{dt.year}_{dt.month:02d}.csv"

        primary_year = self.config.data_dir / year_name
        primary_month = self.config.data_dir / month_name
        backup_year = self.config.backup_dir / f"{dt.year}_bu.csv"
        backup_month = self.config.backup_dir / f"{dt.year}_{dt.month:02d}_bu.csv"

        header = "timestamp,epoch,temperature_c,pressure_hpa,humidity_rh"
        for path in (primary_year, primary_month, backup_year, backup_month):
            self._append_csv(path, header, row)

    @staticmethod
    def _append_csv(path: Path, header: str, row: str) -> None:
        needs_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8") as handle:
            if needs_header:
                handle.write(f"{header}\n")
            handle.write(f"{row}\n")


def main() -> None:
    logger = EnvLogger(Config())

    def handle_signal(_: int, __: object) -> None:
        logger.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.run()


if __name__ == "__main__":
    main()
