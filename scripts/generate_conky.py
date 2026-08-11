#!/usr/bin/env python3
"""
generate_conky.py — Auto-detect hardware and generate conky.conf

Detects CPU (cores, topology, temps), disks, NICs, GPU, display resolution,
proxy settings. Scales layout to fit any screen. Picks a random color scheme.

Usage:
    python3 generate_conky.py [--output PATH] [--blacklist PATH] [--scheme NAME]
"""

import argparse
import glob
import os
import random
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))
REF_HEIGHT = 2160      # reference display height (4K)
REF_BODY_FONT = 12     # reference body font size at 4K
REF_HEADER_FONT = 15
REF_SMALL_FONT = 10
REF_CLOCK_FONT = 31
REF_CJK_FONT = 12
REF_PANEL_W = 460      # reference panel width at 4K
REF_BAR_H = 10         # reference bar height
REF_GRAPH_H_FULL = 50  # full-width graph height
REF_GRAPH_H_SIDE = 36  # side-by-side graph height

# ── Color Schemes ────────────────────────────────────────────────────────────

SCHEMES = {
    "orange": {
        "name": "Dark / Orange",
        "default_color": "#c8c8c8",
        "color1": "#ff8c00",   # headers
        "color2": "#e07800",   # bars
        "color3": "#808080",   # labels
        "color4": "#7ec8e3",   # emphasis (sky blue)
        "color5": "#ff4444",   # down/warning
        "color6": "#66cc66",   # up/ok
        "bg_color": "#1a1a1a",
        "bg_alpha": 230,
        "grad_lo": "4a9ab8",
        "grad_hi": "7ec8e3",
    },
    "cyan": {
        "name": "Dark / Cyan",
        "default_color": "#c8c8c8",
        "color1": "#00bcd4",
        "color2": "#0097a7",
        "color3": "#808080",
        "color4": "#ffd54f",   # emphasis (amber)
        "color5": "#ff4444",
        "color6": "#66cc66",
        "bg_color": "#1a1a1a",
        "bg_alpha": 230,
        "grad_lo": "c9a030",
        "grad_hi": "ffd54f",
    },
    "green": {
        "name": "Dark / Green",
        "default_color": "#c8c8c8",
        "color1": "#4caf50",
        "color2": "#388e3c",
        "color3": "#808080",
        "color4": "#ce93d8",   # emphasis (lilac)
        "color5": "#ff4444",
        "color6": "#81c784",
        "bg_color": "#1a1a1a",
        "bg_alpha": 230,
        "grad_lo": "9c64a8",
        "grad_hi": "ce93d8",
    },
    "purple": {
        "name": "Dark / Purple",
        "default_color": "#c8c8c8",
        "color1": "#bb86fc",
        "color2": "#9c27b0",
        "color3": "#808080",
        "color4": "#80cbc4",   # emphasis (teal)
        "color5": "#ff4444",
        "color6": "#66cc66",
        "bg_color": "#1a1a1a",
        "bg_alpha": 230,
        "grad_lo": "4e9990",
        "grad_hi": "80cbc4",
    },
    "blue": {
        "name": "Dark / Blue",
        "default_color": "#c8c8c8",
        "color1": "#42a5f5",
        "color2": "#1976d2",
        "color3": "#808080",
        "color4": "#ffab91",   # emphasis (peach)
        "color5": "#ff4444",
        "color6": "#66cc66",
        "bg_color": "#1a1a1a",
        "bg_alpha": 230,
        "grad_lo": "c97a60",
        "grad_hi": "ffab91",
    },
    "red": {
        "name": "Dark / Red",
        "default_color": "#c8c8c8",
        "color1": "#ef5350",
        "color2": "#d32f2f",
        "color3": "#808080",
        "color4": "#81d4fa",   # emphasis (light blue)
        "color5": "#ff6659",
        "color6": "#66cc66",
        "bg_color": "#1a1a1a",
        "bg_alpha": 230,
        "grad_lo": "4a9fc8",
        "grad_hi": "81d4fa",
    },
    "teal": {
        "name": "Dark / Teal",
        "default_color": "#c8c8c8",
        "color1": "#26a69a",
        "color2": "#00796b",
        "color3": "#808080",
        "color4": "#f48fb1",   # emphasis (pink)
        "color5": "#ff4444",
        "color6": "#80cbc4",
        "bg_color": "#1a1a1a",
        "bg_alpha": 230,
        "grad_lo": "c06080",
        "grad_hi": "f48fb1",
    },
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def threshold_color(expr, lo, hi):
    """Generate conky if_match color: green < lo, color4 lo..hi, red > hi.

    expr: conky expression returning a number (e.g. '${cpu cpu0}', '${freq 1}')
    lo:   value below which color is green (color6)
    hi:   value above which color is red (color5)
    """
    return (f"${{if_match {expr} > {hi}}}${{color5}}"
            f"${{else}}${{if_match {expr} > {lo}}}${{color4}}"
            f"${{else}}${{color6}}${{endif}}${{endif}}")


def run(cmd, default=""):
    """Run a shell command, return stdout stripped."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else default
    except Exception:
        return default


def read_file(path, default=""):
    try:
        return Path(path).read_text().strip()
    except Exception:
        return default


# ── Hardware Detection ───────────────────────────────────────────────────────

def detect_cpu():
    """Detect CPU via vendor-specific engine and return a dict for compatibility.

    Delegates to engines.detect_cpu_engine() which picks AmdCpuEngine or
    IntelCpuEngine based on /proc/cpuinfo. The engine handles vendor-specific
    temp sensor mapping, model name cleanup, and CCD temp keys.
    """
    from engines import detect_cpu_engine
    eng = detect_cpu_engine()
    eng.detect()
    return {
        "model": eng.model,
        "cores": eng.cores,
        "threads": eng.threads,
        "ccd_groups": eng.ccd_groups,
        "has_ccds": eng.has_ccds,
        "hwmon_idx": eng.hwmon_idx,
        "hwmon_driver": eng.hwmon_driver,
        "temp_sensors": eng.temp_sensors,
        "max_freq_mhz": eng.max_freq_mhz,
        "_engine": eng,  # keep engine reference for gen_cpu_section
    }


def detect_disks(blacklist):
    """Detect mounted filesystems and block devices."""
    disks = []
    # Get mounted filesystems
    lines = run("df -h --output=source,fstype,size,target | grep '^/dev'").splitlines()
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        source = parts[0]       # /dev/nvme1n1p2
        fstype = parts[1]
        size = parts[2]
        mount = parts[3]

        # Skip boot/EFI partitions (not useful to monitor)
        if mount.startswith("/boot"):
            continue

        # Extract base device name
        dev_name = re.sub(r"p?\d+$", "", os.path.basename(source))
        if dev_name in blacklist:
            continue

        # Get model
        model = read_file(f"/sys/block/{dev_name}/device/model",
                          read_file(f"/sys/class/block/{dev_name}/device/model", dev_name))

        # Get transport type for I/O threshold estimation
        tran = run(f"lsblk -dno TRAN /dev/{dev_name} 2>/dev/null").strip()
        # Approximate max throughput in KiB/s: NVMe ~3500MB/s, SATA ~550MB/s
        if tran == "nvme":
            max_io_kib = 3500 * 1024
        elif tran == "sata":
            max_io_kib = 550 * 1024
        else:
            max_io_kib = 1000 * 1024
        io_warn = int(max_io_kib * 0.80)

        disks.append({
            "name": dev_name,
            "dev": source,
            "model": model.strip(),
            "size": size,
            "mount": mount,
            "fstype": fstype,
            "io_warn_kib": io_warn,
        })

    return disks


def detect_nics(blacklist):
    """Detect network interfaces."""
    nics = []
    for iface_dir in sorted(glob.glob("/sys/class/net/*")):
        name = os.path.basename(iface_dir)
        if name in blacklist:
            continue

        # Determine type
        if name == "lo":
            nic_type = "Loopback"
        elif os.path.exists(f"{iface_dir}/wireless"):
            nic_type = "WiFi"
        else:
            nic_type = "Ethernet"

        # Check if up
        operstate = read_file(f"{iface_dir}/operstate", "down")
        is_up = operstate == "up"

        # Link speed in Mbps (-1 or missing = unknown)
        speed_str = read_file(f"{iface_dir}/speed", "-1")
        try:
            link_speed = int(speed_str)
        except ValueError:
            link_speed = -1
        if link_speed <= 0:
            link_speed = 1000  # default 1Gbps

        nics.append({
            "name": name,
            "type": nic_type,
            "is_up": is_up,
            "link_speed_mbps": link_speed,
        })

    # Sort: UP interfaces first, then by type (WiFi > Ethernet > Loopback)
    type_order = {"WiFi": 0, "Ethernet": 1, "Loopback": 2}
    nics.sort(key=lambda n: (0 if n["is_up"] else 1, type_order.get(n["type"], 9)))
    return nics


def detect_gpu():
    """Detect GPU (NVIDIA via nvidia-smi, or lspci fallback)."""
    has_smi = shutil.which("nvidia-smi") is not None
    if has_smi:
        info = run("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits")
        if info:
            parts = [x.strip() for x in info.split(",")]
            return {
                "vendor": "nvidia",
                "model": parts[0] if parts else "NVIDIA GPU",
                "vram_mb": int(parts[1]) if len(parts) > 1 else 0,
                "has_smi": True,
            }

    # Check lspci for any GPU
    lspci = run("lspci | grep -iE 'vga|3d|display'")
    if "nvidia" in lspci.lower():
        model = re.search(r"\[(.+?)\]", lspci)
        return {
            "vendor": "nvidia",
            "model": model.group(1) if model else "NVIDIA GPU",
            "vram_mb": 0,
            "has_smi": False,
        }
    elif "amd" in lspci.lower() or "radeon" in lspci.lower():
        model = re.search(r"\[(.+?)\]", lspci)
        return {
            "vendor": "amd",
            "model": model.group(1) if model else "AMD GPU",
            "vram_mb": 0,
            "has_smi": False,
        }

    return None


def detect_display():
    """Detect display resolution."""
    xrandr = run("xrandr 2>/dev/null | grep ' connected' | head -1")
    m = re.search(r"(\d+)x(\d+)", xrandr)
    if m:
        return {"width": int(m.group(1)), "height": int(m.group(2))}
    return {"width": 1920, "height": 1080}  # fallback


def detect_proxy():
    """Detect proxy from GNOME settings or environment."""
    # GNOME
    mode = run("gsettings get org.gnome.system.proxy mode 2>/dev/null").strip("'")
    if mode == "manual":
        host = run("gsettings get org.gnome.system.proxy.http host 2>/dev/null").strip("'")
        port = run("gsettings get org.gnome.system.proxy.http port 2>/dev/null")
        if host and port:
            return {"host": host, "port": int(port), "enabled": True}

    # Environment
    for var in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        val = os.environ.get(var, "")
        m = re.search(r"([\w.\-]+):(\d+)", val)
        if m:
            return {"host": m.group(1), "port": int(m.group(2)), "enabled": True}

    return {"host": "", "port": 0, "enabled": False}


def detect_cjk_font():
    """Find a CJK font for Chinese characters."""
    fonts = run("fc-list :lang=zh family")
    for preferred in ("Noto Sans CJK SC", "Noto Sans CJK TC", "WenQuanYi",
                      "Droid Sans Fallback", "Source Han Sans"):
        for line in fonts.splitlines():
            if preferred in line:
                return preferred
    return None


# ── Scaling ──────────────────────────────────────────────────────────────────

class Scale:
    def __init__(self, display_height):
        self.f = display_height / REF_HEIGHT

    def px(self, val):
        return max(1, round(val * self.f))

    def font(self, val):
        return max(6, round(val * self.f))


# ── Config Generation ────────────────────────────────────────────────────────

def gen_config_section(scheme, scale):
    """Generate the conky.config = { ... } section."""
    pw = scale.px(REF_PANEL_W)
    s = scheme
    return f"""conky.config = {{
    -- Position & Size
    alignment = 'top_right',
    gap_x = 5,
    gap_y = {scale.px(40)},
    minimum_width = {pw},
    maximum_width = {pw},

    -- Window
    own_window = true,
    own_window_class = 'Conky',
    own_window_type = 'desktop',
    own_window_transparent = false,
    own_window_argb_visual = true,
    own_window_argb_value = {s['bg_alpha']},
    own_window_colour = '{s['bg_color']}',
    own_window_hints = 'undecorated,below,sticky,skip_taskbar,skip_pager',

    -- Borders & Drawing
    border_width = 0,
    draw_borders = false,
    draw_graph_borders = true,
    draw_outline = false,
    draw_shades = false,
    stippled_borders = 0,

    -- Font
    use_xft = true,
    xftalpha = 1,
    font = 'DejaVu Sans Mono:size={scale.font(REF_BODY_FONT)}',

    -- Behavior
    background = true,
    double_buffer = true,
    no_buffers = true,
    cpu_avg_samples = 2,
    net_avg_samples = 2,
    update_interval = 2.0,
    uppercase = false,
    use_spacer = 'none',
    extra_newline = false,
    short_units = true,
    max_user_text = 65536,

    -- Output
    out_to_console = false,
    out_to_ncurses = false,
    out_to_stderr = false,
    out_to_x = true,

    -- Colors
    default_color = '{s['default_color']}',
    color1 = '{s['color1']}',
    color2 = '{s['color2']}',
    color3 = '{s['color3']}',
    color4 = '{s['color4']}',
    color5 = '{s['color5']}',
    color6 = '{s['color6']}',
}}
"""


def gen_datetime_section(scale, cjk_font):
    """Generate DATE/TIME section."""
    hf = scale.font(REF_HEADER_FONT)
    cf = scale.font(REF_CLOCK_FONT)
    cjkf = scale.font(REF_CJK_FONT)
    lunar_path = SCRIPT_DIR / "lunar.py"

    lines = []
    lines.append(f"${{color1}}${{font DejaVu Sans Mono:bold:size={cf}}}${{time %H:%M:%S}}${{font}}${{color}}"
                 f"${{alignr}}${{color3}}${{font DejaVu Sans Mono:size={hf}}}${{time %A}}${{font}}${{color}}")

    lunar_part = f"${{execi 3600 python3 {lunar_path}}}"
    if cjk_font:
        lunar_part = f"${{font {cjk_font}:size={cjkf}}}{lunar_part}${{font}}"

    lines.append(f"${{color4}}${{font DejaVu Sans Mono:size={hf}}}${{time %Y-%m-%d}}${{font}}${{color}}"
                 f"${{alignr}}${{color3}}{lunar_part}${{color}}")
    lines.append("${color3}${hr 1}${color}")
    return "\n".join(lines)


def gen_system_section(cpu, proxy, scale):
    """Generate SYSTEM section."""
    hf = scale.font(REF_HEADER_FONT)
    g1 = scale.px(132)  # label → value goto
    g2 = scale.px(314)  # second column

    lines = []
    lines.append(f"${{color1}}${{font DejaVu Sans Mono:bold:size={hf}}}SYSTEM${{font}}${{color}}")
    lines.append("${color3}${hr 1}${color}")
    # Static info — dim (default_color)
    lines.append(f"${{color3}}Host${{color}}${{goto {g1}}}${{nodename}}")
    lines.append(f"${{color3}}OS${{color}}${{goto {g1}}}${{execi 3600 lsb_release -ds 2>/dev/null || grep PRETTY_NAME /etc/os-release | cut -d'\"' -f2}}")
    lines.append(f"${{color3}}Kernel${{color}}${{goto {g1}}}${{kernel}}")
    # Dynamic info — bright
    lines.append(f"${{color3}}Uptime${{color}}${{goto {g1}}}${{color4}}${{uptime}}${{color}}")
    lines.append(f"${{color3}}Load${{color}}${{goto {g1}}}${{color4}}${{loadavg}}${{color}}")
    lines.append(f"${{color3}}Processes${{color}}${{goto {g1}}}${{color4}}${{processes}}${{color}} total${{goto {g2}}}${{color4}}${{running_processes}}${{color}} running")
    # RAM: green <30%, color4 30-80%, red >80%
    lines.append(f"${{color3}}RAM${{color}}${{goto {g1}}}"
                 f"{threshold_color('${memperc}', 30, 80)}"
                 f"${{mem}} / ${{memmax}}${{alignr}}${{memperc}}%${{color}}")
    lines.append(f"${{color3}}${{membar {scale.px(REF_BAR_H)}}}${{color}}")
    lines.append(f"${{color3}}Public IP${{color}}${{goto {g1}}}${{execi 300 curl -s --max-time 5 ifconfig.me}}")

    if proxy["enabled"]:
        h, p = proxy["host"], proxy["port"]
        lines.append(f"${{color3}}Proxy${{color}}${{goto {g1}}}${{execi 30 timeout 2 bash -c 'echo >/dev/tcp/{h}/{p}' 2>/dev/null && echo 'ON  {h}:{p}' || echo 'OFF {h}:{p}'}}")

    return "\n".join(lines)


def gen_cpu_section(cpu, scheme, scale):
    """Generate CPU section with per-core bars and optional CCD grouping.

    Uses the CPU engine (cpu['_engine']) for vendor-specific behavior:
    total temp label/key, per-core temp map, CCD temp key, model name cleanup.
    """
    eng = cpu["_engine"]
    hf = scale.font(REF_HEADER_FONT)
    sf = scale.font(REF_SMALL_FONT)
    pw = scale.px(REF_PANEL_W)
    bh = scale.px(REF_BAR_H)
    gh = scale.px(REF_GRAPH_H_FULL)
    g1 = scale.px(132)
    g2 = scale.px(254)
    g3 = scale.px(326)
    glo = scheme["grad_lo"]
    ghi = scheme["grad_hi"]

    has_smt = cpu["threads"] > cpu["cores"]
    core_temp_map = eng.core_temp_map()
    has_core_temps = eng.has_per_core_temps()

    # Frequency thresholds: 30% and 80% of max boost (in MHz, for ${freq})
    freq_lo = int(cpu["max_freq_mhz"] * 0.30)
    freq_hi = int(cpu["max_freq_mhz"] * 0.80)

    model_short = eng.model_short()

    lines = []
    lines.append(f"${{voffset 6}}${{color1}}${{font DejaVu Sans Mono:bold:size={hf}}}CPU${{font}}${{color}}  "
                 f"${{color3}}${{font DejaVu Sans Mono:size={sf}}}{model_short}  {cpu['cores']}C/{cpu['threads']}T${{font}}${{color}}")
    lines.append("${color3}${hr 1}${color}")

    # Total + temp with thresholds (CPU max temp ~95°C: green <30, color4 30-76, red >76)
    temp_str = ""
    if cpu["hwmon_idx"] is not None:
        hi = cpu["hwmon_idx"]
        total_key = eng.total_temp_key()
        total_label = eng.total_temp_label()
        if total_key and total_key in cpu["temp_sensors"]:
            ti = cpu["temp_sensors"][total_key]
            temp_str = (f"${{goto {g2}}}${{color3}}{total_label}${{color}}${{goto {g3}}}"
                        f"{threshold_color(f'${{hwmon {hi} temp {ti}}}', 30, 76)}"
                        f"${{hwmon {hi} temp {ti}}}°C${{color}}")
        elif cpu["temp_sensors"]:
            label, ti = next(iter(cpu["temp_sensors"].items()))
            temp_str = (f"${{goto {g2}}}${{color3}}{label}${{color}}${{goto {g3}}}"
                        f"{threshold_color(f'${{hwmon {hi} temp {ti}}}', 30, 76)}"
                        f"${{hwmon {hi} temp {ti}}}°C${{color}}")

    # Total CPU %: green <30%, color4 30-80%, red >80%
    lines.append(f"${{color3}}Total${{color}}${{goto {g1}}}"
                 f"{threshold_color('${cpu cpu0}', 30, 80)}"
                 f"${{cpu cpu0}}%${{color}}{temp_str}")
    lines.append(f"${{color3}}${{cpugraph cpu0 {gh},{pw} {glo} {ghi} -t}}${{color}}")
    lines.append("${voffset 2}\\")

    # Per-core layout positions (hand-tuned at 4K reference)
    if has_smt:
        # Two bars per line: C01 [bar] XX% [bar] XX% X.XG NN°
        bar_w = scale.px(116)
        g_bar1 = scale.px(36)
        g_pct1 = scale.px(156)
        g_bar2 = scale.px(200)
        g_pct2 = scale.px(322)
        g_freq = scale.px(370) if has_core_temps else None
    else:
        # One bar per line: C01 [====long bar====] XX% X.XG NN°
        bar_w = scale.px(300)
        g_bar1 = scale.px(36)
        g_pct1 = scale.px(340)
        g_freq = scale.px(370) if has_core_temps else None

    for gi, group in enumerate(cpu["ccd_groups"]):
        # CCD header (only if multiple groups)
        if cpu["has_ccds"]:
            ccd_label = f"CCD{gi + 1}"
            first_core = group[0][0]
            last_core = group[-1][0]
            temp_part = ""
            if cpu["hwmon_idx"] is not None:
                ccd_key = eng.ccd_temp_key(gi + 1)
                if ccd_key and ccd_key in cpu["temp_sensors"]:
                    ti = cpu["temp_sensors"][ccd_key]
                    temp_part = f"${{alignr}}${{hwmon {cpu['hwmon_idx']} temp {ti}}}°C"
            lines.append(f"${{color1}}{ccd_label}${{color}}  "
                         f"${{color3}}Cores {first_core}\u2013{last_core}${{color}}{temp_part}")

        for core_pair in group:
            t0 = core_pair[0]      # first thread (Linux ID)
            c0 = t0 + 1            # conky 1-indexed
            core_label = f"C{t0 + 1:02d}" if cpu["cores"] >= 10 else f"C{t0 + 1}"

            if has_smt and len(core_pair) > 1:
                t1 = core_pair[1]
                c1 = t1 + 1
                # Per-core temp at end (both SMT threads share one physical core temp)
                temp_str = ""
                if has_core_temps and t0 in core_temp_map:
                    hi = cpu["hwmon_idx"]
                    ti = core_temp_map[t0]
                    temp_str = (f"${{alignr}}"
                                f"{threshold_color(f'${{hwmon {hi} temp {ti}}}', 30, 76)}"
                                f"${{hwmon {hi} temp {ti}}}°${{color}}")
                freq_part = (f"${{goto {g_freq}}}" if g_freq else "${alignr}") + \
                            f"{threshold_color(f'${{freq {c0}}}', freq_lo, freq_hi)}" \
                            f"${{freq_g {c0}}}G${{color}}"
                lines.append(
                    f"${{color3}}{core_label}${{color}}"
                    f"${{goto {g_bar1}}}${{color3}}${{cpubar cpu{c0} {bh},{bar_w}}}${{color}}"
                    f"${{goto {g_pct1}}}{threshold_color(f'${{cpu cpu{c0}}}', 30, 80)}"
                    f"${{cpu cpu{c0}}}%${{color}}"
                    f"${{goto {g_bar2}}}${{color3}}${{cpubar cpu{c1} {bh},{bar_w}}}${{color}}"
                    f"${{goto {g_pct2}}}{threshold_color(f'${{cpu cpu{c1}}}', 30, 80)}"
                    f"${{cpu cpu{c1}}}%${{color}}"
                    f"{freq_part}"
                    f"{temp_str}"
                )
            else:
                temp_str = ""
                if has_core_temps and t0 in core_temp_map:
                    hi = cpu["hwmon_idx"]
                    ti = core_temp_map[t0]
                    temp_str = (f"${{alignr}}"
                                f"{threshold_color(f'${{hwmon {hi} temp {ti}}}', 30, 76)}"
                                f"${{hwmon {hi} temp {ti}}}°${{color}}")
                freq_part = (f"${{goto {g_freq}}}" if g_freq else "${alignr}") + \
                            f"{threshold_color(f'${{freq {c0}}}', freq_lo, freq_hi)}" \
                            f"${{freq_g {c0}}}G${{color}}"
                lines.append(
                    f"${{color3}}{core_label}${{color}}"
                    f"${{goto {g_bar1}}}${{color3}}${{cpubar cpu{c0} {bh},{bar_w}}}${{color}}"
                    f"${{goto {g_pct1}}}{threshold_color(f'${{cpu cpu{c0}}}', 30, 80)}"
                    f"${{cpu cpu{c0}}}%${{color}}"
                    f"{freq_part}"
                    f"{temp_str}"
                )

        if cpu["has_ccds"] and gi < len(cpu["ccd_groups"]) - 1:
            lines.append("${voffset 4}\\")

    # Top processes — #1 emphasized, rest dim
    lines.append("${voffset 4}\\")
    lines.append("${color3}Top Processes${alignr}CPU%${color}")
    lines.append(f"${{color4}} ${{top name 1}}${{alignr}}${{top cpu 1}}%${{color}}")
    for i in range(2, 6):
        lines.append(f"${{color3}} ${{top name {i}}}${{alignr}}${{top cpu {i}}}%${{color}}")

    return "\n".join(lines)


def gen_disk_section(disks, scheme, scale):
    """Generate DISK section."""
    if not disks:
        return ""
    hf = scale.font(REF_HEADER_FONT)
    bh = scale.px(REF_BAR_H)
    g1 = scale.px(132)
    g2 = scale.px(254)
    g3 = scale.px(338)
    ghs = scale.px(REF_GRAPH_H_SIDE)
    glo = scheme["grad_lo"]
    ghi = scheme["grad_hi"]
    pw = scale.px(REF_PANEL_W)
    half_w = pw // 2 - scale.px(24)  # 206 at 4K ref

    lines = []
    lines.append(f"${{voffset 6}}${{color1}}${{font DejaVu Sans Mono:bold:size={hf}}}DISK${{font}}${{color}}")
    lines.append("${color3}${hr 1}${color}")

    # Group by physical device to avoid duplicate I/O graphs
    seen_devs = set()
    for i, d in enumerate(disks):
        dev_base = d["name"]
        mount = d["mount"]
        label = f"{mount}" if mount else dev_base
        lines.append(f"${{color4}}{label}${{color}}  ${{color3}}{d['model']} · {dev_base}${{color}}")
        if mount:
            lines.append(f"${{color3}}${{fs_bar {bh} {mount}}}${{color}}")
            # Disk usage: green <30%, color4 30-80%, red >80%
            lines.append(f"${{color3}}Used${{color}} "
                         f"{threshold_color(f'${{fs_used_perc {mount}}}', 30, 80)}"
                         f"${{fs_used {mount}}} / ${{fs_size {mount}}}${{alignr}}${{fs_used_perc {mount}}}%${{color}}")
        # Only show I/O graphs once per physical device
        if dev_base not in seen_devs:
            seen_devs.add(dev_base)
            lines.append(f"${{color3}}Read${{color}}${{goto {g1}}}${{color4}}${{diskio_read /dev/{dev_base}}}${{color}}${{goto {g2}}}${{color3}}Write${{color}}${{goto {g3}}}${{color4}}${{diskio_write /dev/{dev_base}}}${{color}}")
            lines.append(f"${{color3}}${{diskiograph_read /dev/{dev_base} {ghs},{half_w} {glo} {ghi} -t -l}}${{color}}"
                         f"${{goto {g2}}}${{color3}}${{diskiograph_write /dev/{dev_base} {ghs},{half_w} {glo} {ghi} -t -l}}${{color}}")
        if i < len(disks) - 1:
            lines.append("${voffset 4}\\")

    return "\n".join(lines)


def gen_network_section(nics, scheme, scale):
    """Generate NETWORK section."""
    if not nics:
        return ""
    hf = scale.font(REF_HEADER_FONT)
    g1 = scale.px(132)
    g2 = scale.px(254)
    g3 = scale.px(338)
    ghs = scale.px(REF_GRAPH_H_SIDE)
    glo = scheme["grad_lo"]
    ghi = scheme["grad_hi"]
    pw = scale.px(REF_PANEL_W)
    half_w = pw // 2 - scale.px(24)  # 206 at 4K ref

    lines = []
    lines.append(f"${{voffset 6}}${{color1}}${{font DejaVu Sans Mono:bold:size={hf}}}NETWORK${{font}}${{color}}")
    lines.append("${color3}${hr 1}${color}")

    for nic in nics:
        n = nic["name"]
        # Bandwidth thresholds in KiB/s: 30% and 80% of link speed
        # link_speed_mbps * 1000 / 8 / 1024 => KiB/s
        bw_lo = int(nic["link_speed_mbps"] * 1000 / 8 / 1024 * 0.30)
        bw_hi = int(nic["link_speed_mbps"] * 1000 / 8 / 1024 * 0.80)
        lines.append(f"${{color4}}{n}${{color}}  ${{color3}}{nic['type']}${{color}}"
                     f"${{alignr}}${{if_up {n}}}${{color6}}UP${{color}}${{else}}${{color5}}DOWN${{color}}${{endif}}")
        lines.append(f"${{if_up {n}}}\\")
        lines.append(f"${{color3}}IP${{color}}${{goto {g1}}}${{addr {n}}}")
        lines.append(f"${{color3}}Down${{color}}${{goto {g1}}}"
                     f"{threshold_color(f'${{downspeedf {n}}}', bw_lo, bw_hi)}"
                     f"${{downspeed {n}}}${{color}}"
                     f"${{goto {g2}}}${{color3}}Up${{color}}${{goto {g3}}}"
                     f"{threshold_color(f'${{upspeedf {n}}}', bw_lo, bw_hi)}"
                     f"${{upspeed {n}}}${{color}}")
        lines.append(f"${{color3}}${{downspeedgraph {n} {ghs},{half_w} {glo} {ghi} -l}}${{color}}"
                     f"${{goto {g2}}}${{color3}}${{upspeedgraph {n} {ghs},{half_w} {glo} {ghi} -l}}${{color}}")
        lines.append("${endif}\\")

    return "\n".join(lines)


def gen_gpu_section(gpu, scheme, scale):
    """Generate GPU section (NVIDIA only for now).

    Uses gpu_stats.sh helper script to query all metrics in one nvidia-smi
    call, writing results to /tmp/conky-gpu/*.  Conky reads via ${cat}.
    This keeps line lengths short and avoids spawning many nvidia-smi processes.
    """
    if not gpu:
        return ""
    hf = scale.font(REF_HEADER_FONT)
    sf = scale.font(REF_SMALL_FONT)
    bh = scale.px(REF_BAR_H)
    g1 = scale.px(132)
    g2 = scale.px(254)
    g3 = scale.px(338)
    gh = scale.px(REF_GRAPH_H_FULL)
    glo = scheme["grad_lo"]
    ghi = scheme["grad_hi"]
    pw = scale.px(REF_PANEL_W)

    lines = []
    lines.append(f"${{voffset 6}}${{color1}}${{font DejaVu Sans Mono:bold:size={hf}}}GPU${{font}}${{color}}  "
                 f"${{color3}}${{font DejaVu Sans Mono:size={sf}}}{gpu['model']}${{font}}${{color}}")
    lines.append("${color3}${hr 1}${color}")

    if gpu["vendor"] == "nvidia" and gpu["has_smi"]:
        gpu_script = SCRIPT_DIR / "gpu_stats.sh"
        cache = "/tmp/conky-gpu"
        # Single execi call runs the helper script every 5s
        lines.append(f"${{execi 5 bash {gpu_script}}}")
        # Temp: green <30°C, color4 30-75°C, red >75°C
        temp_expr = f"${{cat {cache}/temp}}"
        fan_expr = f"${{cat {cache}/fan}}"
        lines.append(f"${{color3}}Temp${{color}}${{goto {g1}}}"
                     f"{threshold_color(temp_expr, 30, 75)}"
                     f"{temp_expr}°C${{color}}"
                     f"${{goto {g2}}}${{color3}}Fan${{color}}${{goto {g3}}}"
                     f"{threshold_color(fan_expr, 30, 80)}"
                     f"{fan_expr}%${{color}}")
        # GPU load: green <30%, color4 30-80%, red >80%
        load_expr = f"${{cat {cache}/gpu_util}}"
        lines.append(f"${{color3}}GPU Load${{color}}${{goto {g1}}}"
                     f"{threshold_color(load_expr, 30, 80)}"
                     f"{load_expr}%${{color}}")
        lines.append(f"${{color3}}${{execigraph 5 \"cat {cache}/gpu_util\" {gh},{pw} {glo} {ghi} -t 100}}${{color}}")
        # VRAM: use utilization for threshold, show used/total
        vram_expr = f"${{cat {cache}/mem_util}}"
        lines.append(f"${{color3}}VRAM${{color}}${{goto {g1}}}"
                     f"{threshold_color(vram_expr, 30, 80)}"
                     f"${{cat {cache}/mem_used}}${{color}} / ${{cat {cache}/mem_total}} MiB")
        lines.append(f"${{color3}}${{execibar 5 cat {cache}/mem_util}}${{color}}")
        # Power: thresholds at 30% and 80% of max power limit
        gpu_max_power = int(float(run(f"nvidia-smi --query-gpu=power.max_limit --format=csv,noheader,nounits", "300")))
        power_lo = int(gpu_max_power * 0.30)
        power_hi = int(gpu_max_power * 0.80)
        power_expr = f"${{cat {cache}/power}}"
        lines.append(f"${{color3}}Power${{color}}${{goto {g1}}}"
                     f"{threshold_color(power_expr, power_lo, power_hi)}"
                     f"{power_expr} W${{color}}"
                     f"${{goto {g2}}}${{color3}}Driver${{color}}${{goto {g3}}}${{cat {cache}/driver}}")
    else:
        lines.append(f"${{color3}}Vendor${{color}}${{goto {g1}}}{gpu['vendor'].upper()}")
        lines.append(f"${{color3}}Model${{color}}${{goto {g1}}}{gpu['model']}")

    return "\n".join(lines)


def gen_wallpaper_section(scale, cjk_font):
    """Generate WALLPAPER section (Bing daily image rotation info)."""
    cache_dir = Path.home() / ".cache" / "bing-wallpaper"
    title_path = cache_dir / "title.txt"
    copyright_path = cache_dir / "copyright.txt"
    cur_date_path = cache_dir / "cur_date.txt"
    next1_title_path = cache_dir / "next1_title.txt"
    next1_countdown_path = cache_dir / "next1_countdown.txt"
    next2_title_path = cache_dir / "next2_title.txt"
    next2_countdown_path = cache_dir / "next2_countdown.txt"
    script_path = SCRIPT_DIR / "bing_wallpaper.py"
    if not title_path.exists():
        return ""

    hf = scale.font(REF_HEADER_FONT)
    sf = scale.font(REF_SMALL_FONT)
    bf = scale.font(REF_BODY_FONT)
    g1 = scale.px(132)

    # CJK fonts for Bing text (titles may contain CJK characters)
    cjk_title = f"font {cjk_font}:size={bf}" if cjk_font else f"font DejaVu Sans Mono:size={bf}"
    cjk_sub = f"font {cjk_font}:size={sf}" if cjk_font else f"font DejaVu Sans Mono:size={sf}"

    lines = []
    # Rotation check — runs every 60s, outputs countdown for display
    lines.append(f"${{voffset 6}}${{color1}}${{font DejaVu Sans Mono:bold:size={hf}}}WALLPAPER${{font}}${{color}}  "
                 f"${{color3}}${{font DejaVu Sans Mono:size={sf}}}Bing Daily${{font}}${{color}}"
                 f"${{alignr}}${{color4}}${{execi 60 python3 {script_path} --check-rotate}}${{color}}")
    lines.append("${color3}${hr 1}${color}")
    lines.append(f"${{{cjk_title}}}${{color4}}${{cat {title_path}}}${{color}}${{font}}"
                 f"${{alignr}}${{color3}}${{cat {cur_date_path}}}${{color}}")
    lines.append(f"${{{cjk_sub}}}${{color3}}${{cat {copyright_path}}}${{color}}${{font}}")
    lines.append(f"${{color4}}${{cat {next1_countdown_path}}}${{color}}"
                 f"${{goto {g1}}}${{{cjk_sub}}}${{cat {next1_title_path}}}${{font}}")
    lines.append(f"${{color4}}${{cat {next2_countdown_path}}}${{color}}"
                 f"${{goto {g1}}}${{{cjk_sub}}}${{cat {next2_title_path}}}${{font}}")
    return "\n".join(lines)


def load_blacklist(path):
    """Load blacklist file. Format: type:name (e.g., disk:nvme0n1, nic:enp39s0).

    Loads the base blacklist file, then merges a per-host override file
    (blacklist-<hostname>.conf) if it exists in the same directory.
    This lets multiple PCs share the repo via git while keeping
    host-specific blacklists separate.
    """
    bl = {"disk": set(), "nic": set()}

    def _load_one(p):
        if not p or not os.path.exists(p):
            return
        for line in Path(p).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                typ, name = line.split(":", 1)
                typ = typ.strip().lower()
                name = name.strip()
                if typ in bl:
                    bl[typ].add(name)

    # Base blacklist (shared, tracked in git)
    _load_one(path)

    # Per-host override (gitignored, machine-specific)
    if path:
        base = Path(path)
        host_file = base.parent / f"blacklist-{socket.gethostname()}.conf"
        _load_one(host_file)

    return bl


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate conky.conf from hardware detection")
    parser.add_argument("--output", "-o", default=os.path.expanduser("~/.config/conky/conky.conf"),
                        help="Output path (default: ~/.config/conky/conky.conf)")
    parser.add_argument("--blacklist", "-b", default=str(SCRIPT_DIR.parent / "blacklist.conf"),
                        help="Blacklist file path")
    parser.add_argument("--scheme", "-s", default=None,
                        help=f"Color scheme: {', '.join(SCHEMES.keys())} (default: random)")
    args = parser.parse_args()

    # Pick color scheme
    if args.scheme and args.scheme in SCHEMES:
        scheme = SCHEMES[args.scheme]
    else:
        scheme = random.choice(list(SCHEMES.values()))
    print(f"Color scheme: {scheme['name']}")

    # Load blacklist (base + per-host override)
    bl = load_blacklist(args.blacklist)
    host_file = Path(args.blacklist).parent / f"blacklist-{socket.gethostname()}.conf"
    if host_file.exists():
        print(f"Host override: {host_file.name}")
    if bl["disk"] or bl["nic"]:
        print(f"Blacklist: disks={bl['disk']}, nics={bl['nic']}")

    # Detect hardware
    print("Detecting hardware...")
    display = detect_display()
    print(f"  Display: {display['width']}x{display['height']}")

    cpu = detect_cpu()
    print(f"  CPU: {cpu['model']} ({cpu['cores']}C/{cpu['threads']}T, "
          f"{len(cpu['ccd_groups'])} CCD(s), hwmon={cpu['hwmon_idx']})")

    disks = detect_disks(bl["disk"])
    print(f"  Disks: {[d['name'] + '(' + d['mount'] + ')' for d in disks]}")

    nics = detect_nics(bl["nic"])
    print(f"  NICs: {[n['name'] + '(' + n['type'] + ')' for n in nics]}")

    gpu = detect_gpu()
    print(f"  GPU: {gpu['model'] if gpu else 'None'}")

    proxy = detect_proxy()
    if proxy["enabled"]:
        print(f"  Proxy: {proxy['host']}:{proxy['port']}")

    cjk_font = detect_cjk_font()
    print(f"  CJK font: {cjk_font or 'None'}")

    # Scale
    scale = Scale(display["height"])
    print(f"  Scale factor: {scale.f:.2f}")

    # Generate config
    sections = [
        gen_config_section(scheme, scale),
        "conky.text = [[",
        gen_datetime_section(scale, cjk_font),
        gen_system_section(cpu, proxy, scale),
        gen_cpu_section(cpu, scheme, scale),
        gen_disk_section(disks, scheme, scale),
        gen_network_section(nics, scheme, scale),
        gen_gpu_section(gpu, scheme, scale),
        gen_wallpaper_section(scale, cjk_font),
        "${voffset 5}",
        "]]",
    ]

    config = "\n".join(s for s in sections if s) + "\n"

    # Write output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(config)
    print(f"\nGenerated: {out_path}")


if __name__ == "__main__":
    main()
