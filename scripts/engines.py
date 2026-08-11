#!/usr/bin/env python3
"""
engines.py — CPU vendor engine framework for conky config generation.

Provides a common base class (CpuEngine) with shared detection logic.
Vendor-specific subclasses live in separate files:
  - PCAmd5950.py   → AmdCpuEngine   (AMD Ryzen, k10temp)
  - PCIntel7960.py → IntelCpuEngine (Intel Core, coretemp)

Usage:
    from engines import detect_cpu_engine
    cpu = detect_cpu_engine()
    cpu.detect()
    # cpu.total_temp_label(), cpu.core_temp_map(), cpu.model_short(), etc.
"""

import glob
import re
from pathlib import Path

# Import helpers from generate_conky (same directory)
import sys
sys.path.insert(0, str(Path(__file__).parent))
from generate_conky import run, read_file


class CpuEngine:
    """Base CPU engine — common detection, vendor-neutral defaults.

    Subclasses override:
      - hwmon_drivers:    set of kernel driver names to match
      - total_temp_label: short label for the total CPU temperature
      - total_temp_key:   key in temp_sensors for total CPU temp
      - core_temp_map:    {linux_core_id: temp_index} for per-core temps
      - ccd_temp_key:     key for a CCD temperature (or None)
      - model_short:      vendor-specific model name cleanup
    """

    hwmon_drivers = set()

    def __init__(self):
        self.model = ""
        self.cores = 0
        self.threads = 0
        self.ccd_groups = []
        self.has_ccds = False
        self.hwmon_idx = None
        self.hwmon_driver = None
        self.temp_sensors = {}  # label -> temp_index
        self.max_freq_mhz = 5000

    # ── Detection (common) ──────────────────────────────────────────────

    def detect(self):
        """Detect CPU model, cores, threads, topology, and temperature sensors."""
        self.model = self._detect_model()
        self.threads = int(run("nproc", "1"))
        cores_per_socket = int(run("lscpu | awk '/^Core\\(s\\) per socket:/{print $NF}'", "1"))
        sockets = int(run("lscpu | awk '/^Socket\\(s\\):/{print $NF}'", "1"))
        self.cores = cores_per_socket * sockets
        self.ccd_groups = self._detect_ccd_groups()
        self.has_ccds = len(self.ccd_groups) > 1
        self._detect_hwmon()
        self.max_freq_mhz = int(read_file(
            "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", "5000000"
        )) // 1000  # KHz -> MHz

    def _detect_model(self):
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
        return "Unknown CPU"

    def _detect_ccd_groups(self):
        """Detect CCD groups by L3 cache ID.

        Each group: [(first_thread, second_thread), ...]
        """
        l3_groups = {}
        for cpu_dir in sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*"),
                              key=lambda x: int(re.search(r"(\d+)$", x).group())):
            cpu_id = int(re.search(r"(\d+)$", cpu_dir).group())
            siblings = read_file(f"{cpu_dir}/topology/thread_siblings_list")
            if not siblings:
                continue
            first = int(siblings.split(",")[0])
            if cpu_id != first:
                continue  # only process first thread of each pair
            try:
                l3_id = int(read_file(f"{cpu_dir}/cache/index3/id", "0"))
            except ValueError:
                l3_id = 0
            sib_list = [int(x) for x in siblings.split(",")]
            l3_groups.setdefault(l3_id, []).append(sib_list)

        return [l3_groups[k] for k in sorted(l3_groups.keys())]

    def _detect_hwmon(self):
        """Detect hwmon for CPU temp using vendor-specific driver names."""
        for hwmon_dir in glob.glob("/sys/class/hwmon/hwmon*"):
            name = read_file(f"{hwmon_dir}/name")
            if name in self.hwmon_drivers:
                self.hwmon_idx = int(re.search(r"(\d+)$", hwmon_dir).group())
                self.hwmon_driver = name
                for label_file in glob.glob(f"{hwmon_dir}/temp*_label"):
                    m = re.search(r"temp(\d+)_label", label_file)
                    if m:
                        label = read_file(label_file)
                        self.temp_sensors[label] = int(m.group(1))
                # If no labels, try to find any temp input
                if not self.temp_sensors:
                    for inp in glob.glob(f"{hwmon_dir}/temp*_input"):
                        m = re.search(r"temp(\d+)_input", inp)
                        if m:
                            self.temp_sensors.setdefault("CPU", int(m.group(1)))
                break

    # ── Vendor-specific overrides (override in subclasses) ──────────────

    def total_temp_label(self):
        """Short label for the total CPU temperature (e.g. 'Tctl', 'Pkg')."""
        return None

    def total_temp_key(self):
        """Key in temp_sensors for the total CPU temperature."""
        return None

    def core_temp_map(self):
        """Return {linux_core_id: temp_index} for per-core temperatures."""
        return {}

    def has_per_core_temps(self):
        """Whether this CPU exposes per-core temperature sensors."""
        return False

    def ccd_temp_key(self, ccd_idx):
        """Key in temp_sensors for a CCD temperature, or None."""
        return None

    def model_short(self):
        """Return a shortened model name for display."""
        s = self.model
        for remove in ("(R)", "(TM)"):
            s = s.replace(remove, "")
        s = re.sub(r"\s{2,}", " ", s).strip()
        if len(s) > 30:
            s = s[:30]
        return s


# ── Factory ───────────────────────────────────────────────────────────────────

def detect_cpu_engine():
    """Auto-detect CPU vendor from /proc/cpuinfo and return the right engine.

    Vendor engines live in separate files:
      - PCAmd5950.py   → AmdCpuEngine
      - PCIntel7960.py → IntelCpuEngine
    """
    model = ""
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break

    model_lower = model.lower()
    if "amd" in model_lower or "ryzen" in model_lower or "epyc" in model_lower:
        from PCAmd5950 import AmdCpuEngine
        return AmdCpuEngine()
    elif "intel" in model_lower:
        from PCIntel7960 import IntelCpuEngine
        return IntelCpuEngine()
    # Fallback: try to detect by hwmon driver
    for hwmon_dir in glob.glob("/sys/class/hwmon/hwmon*"):
        name = read_file(f"{hwmon_dir}/name")
        if name == "k10temp":
            from PCAmd5950 import AmdCpuEngine
            return AmdCpuEngine()
        if name == "coretemp":
            from PCIntel7960 import IntelCpuEngine
            return IntelCpuEngine()

    return CpuEngine()
