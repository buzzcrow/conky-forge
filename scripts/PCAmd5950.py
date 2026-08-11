#!/usr/bin/env python3
"""
PCAmd5950.py — AMD Ryzen CPU engine for conky config generation.

Specific to AMD Ryzen 9 5950X (k10temp driver):
  - Total temp: Tctl
  - CCD temps: Tccd1, Tccd2, ...
  - No per-core temperature sensors
"""

import re
from engines import CpuEngine


class AmdCpuEngine(CpuEngine):
    """AMD Ryzen CPU engine (k10temp driver).

    - Total temp: Tctl
    - CCD temps: Tccd1, Tccd2, ...
    - No per-core temperature sensors
    """

    hwmon_drivers = {"k10temp"}

    def total_temp_label(self):
        return "Tctl"

    def total_temp_key(self):
        return "Tctl"

    def ccd_temp_key(self, ccd_idx):
        return f"Tccd{ccd_idx}"

    def model_short(self):
        s = self.model
        for remove in ("(R)", "(TM)", "with Radeon Graphics"):
            s = s.replace(remove, "")
        s = re.sub(r"\s{2,}", " ", s).strip()
        if len(s) > 30:
            s = s[:30]
        return s
