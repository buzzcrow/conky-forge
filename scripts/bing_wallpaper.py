#!/usr/bin/env python3
"""
bing_wallpaper.py — Bing daily wallpaper rotator for conky.

Downloads all available Bing wallpapers (~16 images, ~2 weeks of history),
rotates through them on a configurable interval (default 4h), darkens the
right side for conky readability, and writes metadata files for conky display.

Modes:
    python3 bing_wallpaper.py [--market M] [--interval H]
        Startup mode: download gallery, set current wallpaper.
        Called from start_conky.sh.

    python3 bing_wallpaper.py --check-rotate [--interval H]
        Rotation check: switch wallpaper if interval elapsed, print countdown.
        Called by conky ${execi} every ~60s.

Dependencies:
    - python3 (standard library + optional Pillow for gradient)
    - gsettings (GNOME desktop)
"""

import argparse
import calendar
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

# ── Layout ────────────────────────────────────────────────────────────────────
CONKY_CONF = Path.home() / ".config" / "conky" / "conky.conf"

# ── Paths ────────────────────────────────────────────────────────────────────
CACHE_DIR = Path.home() / ".cache" / "bing-wallpaper"
GALLERY_DIR = CACHE_DIR / "gallery"
GALLERY_JSON = CACHE_DIR / "gallery.json"
WALLPAPER_OUT = CACHE_DIR / "wallpaper.jpg"
DATE_STAMP = CACHE_DIR / ".date"
SLOT_FILE = CACHE_DIR / ".slot"

# Conky display files
TITLE_FILE = CACHE_DIR / "title.txt"
COPYRIGHT_FILE = CACHE_DIR / "copyright.txt"
COUNTDOWN_FILE = CACHE_DIR / "countdown.txt"
CUR_DATE_FILE = CACHE_DIR / "cur_date.txt"
NEXT1_TITLE_FILE = CACHE_DIR / "next1_title.txt"
NEXT1_COUNTDOWN_FILE = CACHE_DIR / "next1_countdown.txt"
NEXT2_TITLE_FILE = CACHE_DIR / "next2_title.txt"
NEXT2_COUNTDOWN_FILE = CACHE_DIR / "next2_countdown.txt"

# Legacy files (kept for compat, no longer generated)
PREV_TITLE_FILE = CACHE_DIR / "prev_title.txt"
NEXT_TITLE_FILE = CACHE_DIR / "next_title.txt"
PREV_DATE_FILE = CACHE_DIR / "prev_date.txt"
NEXT_DATE_FILE = CACHE_DIR / "next_date.txt"
DISPLAY_TIME_FILE = CACHE_DIR / "display_time.txt"
PREV_TIME_FILE = CACHE_DIR / "prev_time.txt"
NEXT_TIME_FILE = CACHE_DIR / "next_time.txt"

BING_API = "https://www.bing.com/HPImageArchive.aspx?format=js&idx={idx}&n=8&mkt={market}"
DEFAULT_INTERVAL = 0.5  # hours (30 minutes)


# ── Helpers ──────────────────────────────────────────────────────────────────

def read_conky_layout():
    """Read gap_x and panel width from generated conky.conf."""
    gap_x, panel_w = 0, 460  # fallback defaults
    if CONKY_CONF.exists():
        text = CONKY_CONF.read_text()
        m = re.search(r'gap_x\s*=\s*(\d+)', text)
        if m:
            gap_x = int(m.group(1))
        m = re.search(r'minimum_width\s*=\s*(\d+)', text)
        if m:
            panel_w = int(m.group(1))
    return gap_x, panel_w


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def detect_resolution():
    out = run("xrandr 2>/dev/null | grep ' connected' | head -1")
    m = re.search(r"(\d+)x(\d+)", out)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 1920, 1080


def detect_proxy():
    mode = run("gsettings get org.gnome.system.proxy mode 2>/dev/null").strip("' ")
    if mode == "manual":
        host = run("gsettings get org.gnome.system.proxy.http host 2>/dev/null").strip("' ")
        port = run("gsettings get org.gnome.system.proxy.http port 2>/dev/null").strip()
        if host and port and port != "0":
            return f"http://{host}:{port}"
    for var in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        val = os.environ.get(var, "")
        if val:
            return val
    return None


def url_open(url, timeout=15):
    proxy = detect_proxy()
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        opener = urllib.request.build_opener()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return opener.open(req, timeout=timeout)


def format_countdown(seconds):
    """Format seconds into human-readable countdown."""
    if seconds <= 0:
        return "now"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    if m > 0:
        return f"{m}m"
    return "< 1m"


# ── Gallery Download ─────────────────────────────────────────────────────────

def download_gallery(market="en-US"):
    """Download all available Bing wallpapers (~16) and save metadata."""
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    gallery = []
    seen = set()

    print(f"Downloading Bing wallpaper gallery (market={market})...")

    # Bing API: idx=offset, n=count (max 8 per request)
    for idx in range(0, 16, 8):
        api_url = BING_API.format(idx=idx, market=market)
        try:
            with url_open(api_url, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"  WARN: API request idx={idx} failed: {e}", file=sys.stderr)
            continue

        for img in data.get("images", []):
            urlbase = img.get("urlbase", "")
            if not urlbase or urlbase in seen:
                continue
            seen.add(urlbase)
            gallery.append({
                "urlbase": urlbase,
                "title": img.get("title", "").strip(),
                "copyright": img.get("copyright", "").strip(),
                "copyrightlink": img.get("copyrightlink", "").strip(),
                "date": img.get("startdate", ""),
            })

    if not gallery:
        print("ERROR: No images from Bing API", file=sys.stderr)
        return False

    print(f"  Found {len(gallery)} unique images, downloading...")

    # Download each image
    ok_count = 0
    for i, entry in enumerate(gallery):
        img_path = GALLERY_DIR / f"{i}.jpg"
        if img_path.exists() and img_path.stat().st_size > 10000:
            # Reuse cached image if gallery order hasn't changed
            old_gallery = _load_gallery()
            if old_gallery and i < len(old_gallery) and old_gallery[i].get("urlbase") == entry["urlbase"]:
                ok_count += 1
                continue

        urlbase = entry["urlbase"]
        downloaded = False
        for suffix in ("_UHD.jpg", "_1920x1080.jpg"):
            img_url = f"https://www.bing.com{urlbase}{suffix}"
            try:
                with url_open(img_url, timeout=30) as resp:
                    data = resp.read()
                if data[:2] == b"\xff\xd8":
                    img_path.write_bytes(data)
                    downloaded = True
                    ok_count += 1
                    break
            except Exception:
                continue

        status = "ok" if downloaded else "FAILED"
        print(f"  [{i:2d}] {entry['title'][:40]:40s} {status}")

    # Save gallery metadata
    GALLERY_JSON.write_text(json.dumps(gallery, ensure_ascii=False, indent=2))
    DATE_STAMP.write_text(str(date.today()))
    print(f"  Gallery: {ok_count}/{len(gallery)} images ready")
    return ok_count > 0


def _load_gallery():
    """Load gallery metadata from cache."""
    if GALLERY_JSON.exists():
        try:
            return json.loads(GALLERY_JSON.read_text())
        except Exception:
            pass
    return []


def is_gallery_fresh():
    """Check if gallery was downloaded today."""
    if DATE_STAMP.exists() and GALLERY_JSON.exists():
        return DATE_STAMP.read_text().strip() == str(date.today())
    return False


# ── Rotation Logic ───────────────────────────────────────────────────────────

def _utc_midnight():
    """Epoch seconds of today's UTC midnight."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(calendar.timegm(midnight.timetuple()))


def calc_slot(interval_hours, num_images):
    """Current rotation slot: starts at 0 (today) at UTC midnight, advances every interval."""
    interval_sec = interval_hours * 3600
    elapsed = time.time() - _utc_midnight()
    return int(elapsed // interval_sec) % num_images


def calc_countdown(interval_hours):
    """Seconds remaining until next rotation."""
    interval_sec = interval_hours * 3600
    elapsed = time.time() - _utc_midnight()
    slot_elapsed = elapsed % interval_sec
    return interval_sec - slot_elapsed


def get_stored_slot():
    """Read the last-applied slot number from disk."""
    if SLOT_FILE.exists():
        try:
            return int(SLOT_FILE.read_text().strip())
        except Exception:
            pass
    return -1


def _format_date(raw):
    """Format '20260411' → '2026-04-11'."""
    if raw and len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw or ""


def _calc_display_times(interval_hours):
    """Calculate local start times for prev/current/next slots."""
    interval_sec = interval_hours * 3600
    utc_mid = _utc_midnight()
    elapsed = time.time() - utc_mid
    raw_slot = int(elapsed // interval_sec)
    fmt = lambda epoch: datetime.fromtimestamp(epoch).strftime("%H:%M")
    return (fmt(utc_mid + (raw_slot - 1) * interval_sec),
            fmt(utc_mid + raw_slot * interval_sec),
            fmt(utc_mid + (raw_slot + 1) * interval_sec))


def write_conky_files(gallery, slot, interval_hours):
    """Write all conky display files for current + next two + countdown."""
    n = len(gallery)
    cur = gallery[slot]
    nxt1 = gallery[(slot + 1) % n]
    nxt2 = gallery[(slot + 2) % n]

    TITLE_FILE.write_text(cur.get("title") or "Bing Wallpaper")
    COPYRIGHT_FILE.write_text(cur.get("copyright") or "")
    CUR_DATE_FILE.write_text(_format_date(cur.get("date")))

    countdown_sec = calc_countdown(interval_hours)
    interval_sec = interval_hours * 3600
    COUNTDOWN_FILE.write_text(format_countdown(countdown_sec))
    NEXT1_TITLE_FILE.write_text(nxt1.get("title") or "")
    NEXT1_COUNTDOWN_FILE.write_text(format_countdown(countdown_sec))
    NEXT2_TITLE_FILE.write_text(nxt2.get("title") or "")
    NEXT2_COUNTDOWN_FILE.write_text(format_countdown(countdown_sec + interval_sec))


# ── Image Processing ─────────────────────────────────────────────────────────

def process_image(src_path, dst_path, screen_w, screen_h):
    """Resize and crop image to screen resolution."""
    # Try Pillow
    try:
        from PIL import Image
        img = Image.open(src_path).convert("RGB")
        ratio = img.width / img.height
        scr_ratio = screen_w / screen_h
        if ratio > scr_ratio:
            nw, nh = int(ratio * screen_h), screen_h
        else:
            nw, nh = screen_w, int(screen_w / ratio)
        img = img.resize((nw, nh), Image.LANCZOS)
        l, t = (nw - screen_w) // 2, (nh - screen_h) // 2
        img = img.crop((l, t, l + screen_w, t + screen_h))
        img.save(dst_path, "JPEG", quality=95)
        return True
    except ImportError:
        pass
    except Exception as e:
        print(f"  Pillow failed: {e}", file=sys.stderr)

    # Try ImageMagick
    try:
        subprocess.check_call([
            "convert", str(src_path),
            "-resize", f"{screen_w}x{screen_h}^",
            "-gravity", "center", "-extent", f"{screen_w}x{screen_h}",
            "-quality", "95", str(dst_path),
        ])
        return True
    except Exception:
        pass

    # Fallback
    shutil.copy2(src_path, dst_path)
    return True


# ── Set Wallpaper ────────────────────────────────────────────────────────────

def set_wallpaper():
    uri = f"file://{WALLPAPER_OUT}"
    for key in ("picture-uri", "picture-uri-dark"):
        try:
            subprocess.check_call([
                "gsettings", "set", "org.gnome.desktop.background", key, uri
            ])
        except Exception:
            pass
    subprocess.call([
        "gsettings", "set", "org.gnome.desktop.background",
        "picture-options", "zoom"
    ])


# ── Apply Slot ───────────────────────────────────────────────────────────────

def apply_slot(slot, gallery, screen_w, screen_h, interval_hours):
    """Process image for slot, set wallpaper, write conky files."""
    src = GALLERY_DIR / f"{slot}.jpg"
    if not src.exists():
        print(f"  WARN: Gallery image {slot}.jpg missing", file=sys.stderr)
        return False

    process_image(src, WALLPAPER_OUT, screen_w, screen_h)
    set_wallpaper()
    SLOT_FILE.write_text(str(slot))
    write_conky_files(gallery, slot, interval_hours)
    return True


# ── Main: init mode ──────────────────────────────────────────────────────────

def cmd_init(args):
    """Startup: download gallery + set wallpaper for current slot."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)

    screen_w, screen_h = detect_resolution()
    print(f"Screen: {screen_w}x{screen_h}")

    if not is_gallery_fresh():
        if not download_gallery(args.market):
            if not _load_gallery():
                print("ERROR: No wallpaper available", file=sys.stderr)
                sys.exit(1)
            print("Using previously cached gallery.")
    else:
        print("Gallery already up to date.")

    gallery = _load_gallery()
    if not gallery:
        print("ERROR: Empty gallery", file=sys.stderr)
        sys.exit(1)

    slot = calc_slot(args.interval, len(gallery))
    print(f"Rotation: slot {slot}/{len(gallery)}, interval {args.interval}h, "
          f"next change in {format_countdown(calc_countdown(args.interval))}")

    apply_slot(slot, gallery, screen_w, screen_h, args.interval)
    print(f"Wallpaper set: [{slot}] {gallery[slot]['title']}")


# ── Main: check-rotate mode ─────────────────────────────────────────────────

def cmd_check_rotate(args):
    """Periodic check: rotate if needed, always update countdown. Print countdown."""
    gallery = _load_gallery()
    if not gallery:
        print("")
        return

    slot = calc_slot(args.interval, len(gallery))
    countdown = format_countdown(calc_countdown(args.interval))

    # Always refresh gallery once per day
    if not is_gallery_fresh():
        try:
            download_gallery(args.market)
            gallery = _load_gallery()
            if not gallery:
                print(countdown)
                return
        except Exception:
            pass

    stored = get_stored_slot()
    if slot != stored:
        # Time to rotate
        screen_w, screen_h = detect_resolution()
        apply_slot(slot, gallery, screen_w, screen_h, args.interval)
    else:
        # Just update conky display files (countdown changes)
        write_conky_files(gallery, slot, args.interval)

    # Output countdown for conky ${execi} capture
    print(countdown)


# ── Entry Point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bing wallpaper rotator for conky")
    parser.add_argument("--market", default="en-US",
                        help="Bing market code (default: en-US)")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                        help=f"Rotation interval in hours (default: {DEFAULT_INTERVAL})")
    parser.add_argument("--check-rotate", action="store_true",
                        help="Check rotation and print countdown (for conky execi)")
    args = parser.parse_args()

    if args.check_rotate:
        cmd_check_rotate(args)
    else:
        cmd_init(args)


if __name__ == "__main__":
    main()
