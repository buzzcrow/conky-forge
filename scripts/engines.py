#!/usr/bin/env python3
"""
engines.py — CPU vendor engines for conky config generation.

Provides a common base class (CpuEngine) with shared detection logic,
and vendor-specific subclasses (AmdCpuEngine, IntelCpuEngine) that
override temperature sensor mapping, model name cleanup, and other
vendor-specific behavior.

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


# ── Factory ───────────────────────────────────────────────────────────────────

def detect_cpu_engine():
    """Auto-detect CPU vendor from /proc/cpuinfo and return the right engine."""
    model = ""
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break

    model_lower = model.lower()
    if "amd" in model_lower or "ryzen" in model_lower or "epyc" in model_lower:
        return AmdCpuEngine()
    elif "intel" in model_lower:
        return IntelCpuEngine()
    # Fallback: try to detect by hwmon driver
    for hwmon_dir in glob.glob("/sys/class/hwmon/hwmon*"):
        name = read_file(f"{hwmon_dir}/name")
        if name == "k10temp":
            return AmdCpuEngine()
        if name == "coretemp":
            return IntelCpuEngine()

    return CpuEngine()
