#!/usr/bin/env python3
"""Chinese lunar calendar (nongli) — zero dependencies.

Lookup table covers 1900-2100.  Each entry encodes:
  bits 0-3   : leap month (0 = no leap)
  bits 4-15  : 12 month lengths, bit=1 → 30 days, bit=0 → 29 days
               (month 1 is the highest bit)
  bit 16     : leap month length, 1 → 30, 0 → 29
  bits 17-20 : day-of-Jan-1 offset (Spring Festival in Jan/Feb)
               stored separately in SPRING list

Output: one line, e.g. "乙巳蛇年 闰六月十五"
"""

import datetime, sys

# fmt: off
# Compact lunar info 1900-2100  (hex)
# Source: widely-used public-domain table
LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,  # 1900-1909
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,  # 1910-1919
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,  # 1920-1929
    0x06566, 0x0d4a0, 0x0ea50, 0x16a95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,  # 1930-1939
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,  # 1940-1949
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0,  # 1950-1959
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,  # 1960-1969
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,  # 1970-1979
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,  # 1980-1989
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x05ac0, 0x0ab60, 0x096d5, 0x092e0,  # 1990-1999
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,  # 2000-2009
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,  # 2010-2019
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,  # 2020-2029
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,  # 2030-2039
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,  # 2040-2049
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06aa0, 0x1a6c4, 0x0aae0,  # 2050-2059
    0x092e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,  # 2060-2069
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,  # 2070-2079
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,  # 2080-2089
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a4d0, 0x0d150, 0x0f252,  # 2090-2099
    0x0d520,  # 2100
]

# Spring Festival dates (month, day) for 1900-2100
SPRING = [
    (1,31),(2,19),(2,8),(1,29),(2,16),(2,4),(1,25),(2,13),(2,2),(1,22),  # 1900-1909
    (2,10),(1,30),(2,18),(2,6),(1,26),(2,14),(2,3),(1,23),(2,11),(2,1),  # 1910-1919
    (2,20),(2,8),(1,28),(2,16),(2,5),(1,24),(2,13),(2,2),(1,23),(2,10),  # 1920-1929
    (1,30),(2,17),(2,6),(1,26),(2,14),(2,4),(1,24),(2,11),(1,31),(2,19),  # 1930-1939
    (2,8),(1,27),(2,15),(2,5),(1,25),(2,13),(2,2),(1,22),(2,10),(1,29),  # 1940-1949
    (2,17),(2,6),(1,27),(2,14),(2,3),(1,24),(2,12),(1,31),(2,18),(2,8),  # 1950-1959
    (1,28),(2,15),(2,5),(1,25),(2,13),(2,2),(1,21),(2,9),(1,30),(2,17),  # 1960-1969
    (2,6),(1,27),(2,15),(2,3),(1,23),(2,11),(1,31),(2,18),(2,7),(1,28),  # 1970-1979
    (2,16),(2,5),(1,25),(2,13),(2,2),(2,20),(2,9),(1,29),(2,17),(2,6),  # 1980-1989
    (1,27),(2,15),(2,4),(1,23),(2,10),(1,31),(2,19),(2,7),(1,28),(2,16),  # 1990-1999
    (2,5),(1,24),(2,12),(2,1),(1,22),(2,9),(1,29),(2,18),(2,7),(1,26),  # 2000-2009
    (2,14),(2,3),(1,23),(2,10),(1,31),(2,19),(2,8),(1,28),(2,16),(2,5),  # 2010-2019
    (1,25),(2,12),(2,1),(1,22),(2,10),(1,29),(2,17),(2,6),(1,26),(2,13),  # 2020-2029
    (2,3),(1,23),(2,11),(1,31),(2,19),(2,8),(1,28),(2,15),(2,4),(1,24),  # 2030-2039
    (2,12),(2,1),(1,22),(2,10),(1,30),(2,17),(2,6),(1,26),(2,14),(2,2),  # 2040-2049
    (1,23),(2,11),(1,31),(2,19),(2,8),(1,28),(2,16),(2,4),(1,24),(2,12),  # 2050-2059
    (2,2),(1,21),(2,9),(1,29),(2,17),(2,6),(1,26),(2,14),(2,3),(1,23),  # 2060-2069
    (2,11),(1,31),(2,19),(2,7),(1,28),(2,15),(2,5),(1,24),(2,12),(2,2),  # 2070-2079
    (1,22),(2,9),(1,29),(2,17),(2,6),(1,26),(2,14),(2,3),(1,24),(2,10),  # 2080-2089
    (1,30),(2,18),(2,7),(1,27),(2,15),(2,5),(1,25),(2,12),(2,1),(1,21),  # 2090-2099
    (2,9),  # 2100
]
# fmt: on

TIANGAN = "甲乙丙丁戊己庚辛壬癸"
DIZHI   = "子丑寅卯辰巳午未申酉戌亥"
SHENGXIAO = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
MONTH_CN = ["", "正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
DAY_CN = [
    "", "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]


def year_days(yi):
    """Total days in lunar year at index yi."""
    info = LUNAR_INFO[yi]
    leap = info & 0xF
    total = 0
    for m in range(1, 13):
        total += 30 if (info >> (16 - m)) & 1 else 29
    if leap:
        total += 30 if info & 0x10000 else 29
    return total


def leap_month_days(yi):
    info = LUNAR_INFO[yi]
    if info & 0xF:
        return 30 if info & 0x10000 else 29
    return 0


def month_days(yi, month):
    info = LUNAR_INFO[yi]
    return 30 if (info >> (16 - month)) & 1 else 29


def lunar_date(dt):
    """Convert a datetime.date to (lunar_year, lunar_month, lunar_day, is_leap)."""
    base = datetime.date(1900, 1, 31)  # Spring Festival 1900
    offset = (dt - base).days
    if offset < 0:
        return None

    yi = 0
    while yi < len(LUNAR_INFO):
        yd = year_days(yi)
        if offset < yd:
            break
        offset -= yd
        yi += 1

    year = 1900 + yi
    info = LUNAR_INFO[yi]
    leap = info & 0xF

    month = 1
    is_leap = False
    for m in range(1, 13):
        md = month_days(yi, m)
        if offset < md:
            month = m
            break
        offset -= md
        if m == leap:
            lmd = leap_month_days(yi)
            if offset < lmd:
                month = m
                is_leap = True
                break
            offset -= lmd
    else:
        month = 12

    day = offset + 1
    return year, month, day, is_leap


def ganzhi_year(year):
    """Tiangan-Dizhi for a lunar year."""
    tg = TIANGAN[(year - 4) % 10]
    dz = DIZHI[(year - 4) % 12]
    sx = SHENGXIAO[(year - 4) % 12]
    return f"{tg}{dz}{sx}年"


def format_lunar(year, month, day, is_leap):
    yz = ganzhi_year(year)
    lp = "闰" if is_leap else ""
    mc = MONTH_CN[month]
    dc = DAY_CN[day]
    return f"{yz} {lp}{mc}月{dc}"


if __name__ == "__main__":
    today = datetime.date.today()
    result = lunar_date(today)
    if result:
        print(format_lunar(*result))
    else:
        print("--")
