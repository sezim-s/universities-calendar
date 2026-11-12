#!/usr/bin/env python3
"""Build a subscribable .ics calendar from universities.csv.

Usage:
    python3 build_calendar.py universities.csv university_calendar.ics

For each row, two yearly all-day events are created when the data is complete:
the founding anniversary (needs founded_month and founded_day) and the rector's
birthday (needs birth_month and birth_day). Rows with a note in founded_check or
birth_check are left out until the note is cleared, so doubtful dates are never
published by accident. Standard library only.
"""

import csv
import datetime
import hashlib
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "universities.csv"
DST = sys.argv[2] if len(sys.argv) > 2 else "university_calendar.ics"
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
FIRST_YEAR = 2026  # first occurrence shown; the yearly rule takes over from there


def as_int(value):
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


def esc(text):
    """Escape text for an iCalendar property value."""
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


def fold(line):
    """RFC 5545: content lines longer than 75 octets must be folded."""
    parts, current, size, limit = [], "", 0, 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            parts.append(current)
            current, size, limit = ch, n, 74  # continuation lines start with a space
        else:
            current += ch
            size += n
    parts.append(current)
    return "\r\n ".join(parts)


def yearly_event(key, summary, description, month, day):
    # 29 February needs a leap year to start from, so start in 2028 for that date.
    start_year = 2028 if (month, day) == (2, 29) else FIRST_YEAR
    start = datetime.date(start_year, month, day)  # raises ValueError if the date is invalid
    end = start + datetime.timedelta(days=1)
    uid = hashlib.md5(key.encode("utf-8")).hexdigest() + "@university-calendar"
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{STAMP}",
        f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
        f"DTEND;VALUE=DATE:{end:%Y%m%d}",
        f"RRULE:FREQ=YEARLY;BYMONTH={month};BYMONTHDAY={day}",
        f"SUMMARY:{esc(summary)}",
        f"DESCRIPTION:{esc(description)}",
        "TRANSP:TRANSPARENT",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "DESCRIPTION:Tomorrow",
        "TRIGGER:-P1D",
        "END:VALARM",
        "END:VEVENT",
    ]
    return [fold(line) for line in lines]


events, flagged, incomplete = [], [], []
anniversaries = birthdays = 0

with open(SRC, encoding="utf-8-sig", newline="") as f:
    for row in csv.DictReader(f):
        uni = row["university"].strip()
        if not uni:
            continue
        rector = row["rector"].strip()

        # Founding anniversary
        fy = as_int(row["founded_year"])
        fm = as_int(row["founded_month"])
        fd = as_int(row["founded_day"])
        if fm and fd:
            note = row["founded_check"].strip()
            if note:
                flagged.append(f"{uni} (founding date): {note}")
            else:
                try:
                    events += yearly_event(
                        f"anniv|{uni}",
                        f"Founding anniversary: {uni}",
                        f"Founded {fy}." if fy else "Founding anniversary.",
                        fm, fd)
                    anniversaries += 1
                except ValueError:
                    flagged.append(f"{uni} (founding date): {fd}.{fm} is not a valid date")
        elif fy or fm:
            incomplete.append(uni)

        # Rector's birthday
        bm = as_int(row["birth_month"])
        bd = as_int(row["birth_day"])
        if rector and bm and bd:
            note = row["birth_check"].strip()
            if note:
                flagged.append(f"{rector} ({uni}, birthday): {note}")
            else:
                try:
                    events += yearly_event(
                        f"birthday|{uni}|{rector}",
                        f"Birthday: {rector}",
                        f"Head of {uni}.",
                        bm, bd)
                    birthdays += 1
                except ValueError:
                    flagged.append(f"{rector} ({uni}, birthday): {bd}.{bm} is not a valid date")
        elif rector and (bm or as_int(row["birth_year"])):
            incomplete.append(f"{rector} (birthday)")

header = [fold(line) for line in [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//University calendar//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:Universities: anniversaries and rectors' birthdays",
]]

with open(DST, "w", encoding="utf-8", newline="") as f:
    f.write("\r\n".join(header + events + ["END:VCALENDAR"]) + "\r\n")

print(f"Wrote {DST}: {anniversaries} founding anniversaries, {birthdays} rector birthdays.")
if flagged:
    print(f"\nExcluded until fixed in the CSV ({len(flagged)}):")
    for item in flagged:
        print("  -", item)
print(f"\nNot in the calendar because a day or month is missing: "
      f"{len(incomplete)} entries (see the CSV).")
