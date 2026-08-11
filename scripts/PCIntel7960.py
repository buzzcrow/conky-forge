#!/usr/bin/env python3
"""
PCIntel7960.py — Intel CPU engine for conky config generation.

Specific to Intel Core i9-7960X (coretemp driver):
  - Total temp: Package id 0
  - Per-core temps: Core 0, Core 1, ..., Core N-1
  - No CCD grouping (uses L3 cache topology, but typically one group)
"""

import re
from engines import CpuEngine


class IntelCpuEngine(CpuEngine):
    """Intel CPU engine (coretemp driver).

    - Total temp: Package id 0
    - Per-core temps: Core 0, Core 1, ..., Core N-1
    - No CCD grouping (uses L3 cache topology, but typically one group)
    """

    hwmon_drivers = {"coretemp"}

    def total_temp_label(self):
        return "Pkg"

    def total_temp_key(self):
        return "Package id 0"

    def core_temp_map(self):
        """Parse 'Core N' labels into {core_id: temp_index}."""
        result = {}
        for label, ti in self.temp_sensors.items():
            m = re.match(r"Core (\d+)$", label)
            if m:
                result[int(m.group(1))] = ti
        return result

    def has_per_core_temps(self):
        return len(self.core_temp_map()) > 0

    def model_short(self):
        s = self.model
        for remove in ("(R)", "(TM)", "Processor", "CPU"):
            s = s.replace(remove, "")
        s = re.sub(r"\s{2,}", " ", s).strip()
        if len(s) > 30:
            s = s[:30]
        return s
