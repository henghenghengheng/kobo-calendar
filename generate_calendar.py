#!/usr/bin/env python3
import datetime
import requests
from icalendar import Calendar
import pytz
from dateutil.rrule import rrulestr
import re
import os

SG_TZ = pytz.timezone("Asia/Singapore")

# -----------------------------
# Fetch ICS
# -----------------------------
def fetch_calendar(url):
    print("Fetching ICS calendar...")
    r = requests.get(url)
    print(f"ICS fetch status code: {r.status_code}")
    r.raise_for_status()
    return Calendar.from_ical(r.text)

# -----------------------------
# Parse events (with recurrence)
# -----------------------------
def parse_events(cal, start_range=None, end_range=None):
    """
    Parse VEVENTs from calendar and expand recurrences within optional range.
    Returned datetimes are converted to Asia/Singapore timezone for display.
    """
    print("Parsing events...")
    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("summary", "")).strip()
        location = str(component.get("location", "") or "").strip()

        # dtstart/dtend can be date or datetime objects from icalendar
        raw_dtstart = component.get("dtstart").dt
        raw_dtend = component.get("dtend").dt

        # Handle all-day (date) events -> convert to datetime at midnight
        all_day = False
        if isinstance(raw_dtstart, datetime.date) and not isinstance(raw_dtstart, datetime.datetime):
            all_day = True
            raw_dtstart = datetime.datetime.combine(raw_dtstart, datetime.time.min)
        if isinstance(raw_dtend, datetime.date) and not isinstance(raw_dtend, datetime.datetime):
            all_day = True
            raw_dtend = datetime.datetime.combine(raw_dtend, datetime.time.min)

        # Ensure tz-aware: if naive assume UTC (common for exported ICS). If tz-aware, keep tzinfo.
        if raw_dtstart.tzinfo is None:
            raw_dtstart = raw_dtstart.replace(tzinfo=pytz.UTC)
        if raw_dtend.tzinfo is None:
            raw_dtend = raw_dtend.replace(tzinfo=pytz.UTC)

        # Recurrence handling
        rrule_val = component.get("RRULE")
        if rrule_val:
            # Build RRULE string from the mapping while trying to avoid weird numeric tokens
            parts = []
            for k, v in rrule_val.items():
                # v is often a list; take first
                val = str(v[0])
                if val == "":
                    continue
                # Skip numeric-only tokens that dateutil chokes on (some calendars emit weird tokens)
                if re.fullmatch(r"\d+", val):
                    # skip numeric-only token
                    continue
                parts.append(f"{k}={val}")
            rrule_str_clean = ";".join(parts)

            try:
                # Use original dtstart (with tz) so rrules are generated correctly
                rule = rrulestr(rrule_str_clean, dtstart=raw_dtstart)
                if start_range and end_range:
                    occs = list(rule.between(start_range, end_range, inc=True))
                else:
                    occs = list(rule)

                for occ in occs:
                    # occ will be tz-aware (same tz as dtstart). Convert to SG for display.
                    occ_start_sg = occ.astimezone(SG_TZ)
                    occ_end_sg = (occ + (raw_dtend - raw_dtstart)).astimezone(SG_TZ)
                    events.append({
                        "summary": summary,
                        "location": location,
                        "start": occ_start_sg,
                        "end": occ_end_sg,
                        "all_day": all_day
                    })
            except Exception as exc:
                print(f"Warning: unsupported RRULE for '{summary}' -> {exc}. Falling back to single instance.")
                # fallback: use single instance (converted to SG)
                events.append({
                    "summary": summary,
                    "location": location,
                    "start": raw_dtstart.astimezone(SG_TZ),
                    "end": raw_dtend.astimezone(SG_TZ),
                    "all_day": all_day
                })
        else:
            # Non-recurring: convert to SG timezone for display
            events.append({
                "summary": summary,
                "location": location,
                "start": raw_dtstart.astimezone(SG_TZ),
                "end": raw_dtend.astimezone(SG_TZ),
                "all_day": all_day
            })

        print(f"Parsed event: {summary}, start={events[-1]['start']}, end={events[-1]['end']}, all_day={events[-1]['all_day']}")

    print(f"Total events parsed/expanded: {len(events)}")
    return events

# -----------------------------
# Utility: get week bounds (Sunday -> Saturday)
# -----------------------------
def week_bounds_for(date_dt):
    """Return (start_of_week, end_of_week) in same tz as date_dt. start at 00:00 Sunday, end at 23:59:59 Saturday."""
    if date_dt.tzinfo is None:
        date_dt = date_dt.replace(tzinfo=SG_TZ)

    # Python weekday(): Monday=0 ... Sunday=6
    weekday = date_dt.weekday()
    days_to_sunday = (weekday + 1) % 7
    start_of_week = (date_dt - datetime.timedelta(days=days_to_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + datetime.timedelta(days=6, hours=23, minutes=59, seconds=59)
    return start_of_week, end_of_week

# -----------------------------
# Filter events for the week
# -----------------------------
def filter_week(events, reference_date=None):
    if reference_date is None:
        reference_date = datetime.datetime.now(SG_TZ)
    elif reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=SG_TZ)

    start_of_week, end_of_week = week_bounds_for(reference_date)

    week_events = []
    for e in events:
        s = e['start']
        t = e['end']
        # ensure tz-aware and in SG
        if s.tzinfo is None:
            s = s.replace(tzinfo=pytz.UTC).astimezone(SG_TZ)
        if t.tzinfo is None:
            t = t.replace(tzinfo=pytz.UTC).astimezone(SG_TZ)

        # overlap check
        if t >= start_of_week and s <= end_of_week:
            e_copy = e.copy()
            # clamp to week bounds (for display)
            if s < start_of_week:
                e_copy['start'] = start_of_week
            else:
                e_copy['start'] = s
            if t > end_of_week:
                e_copy['end'] = end_of_week
            else:
                e_copy['end'] = t
            week_events.append(e_copy)

    print(f"Events this week: {len(week_events)} (week {start_of_week.date()} → {end_of_week.date()})")
    return week_events, start_of_week

# -----------------------------
# Generate HTML with proper timezone & header offset
# -----------------------------
def generate_html(events, start_of_week):
    days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

    # Separate all-day vs timed
    all_day_events = [e for e in events if e['all_day']]
    timed_events = [e for e in events if not e['all_day']]

    # Determine timeline start/end in SG tz
    if timed_events:
        earliest = min(e['start'] for e in timed_events)
        latest = max(e['end'] for e in timed_events)
        # round timeline start down to hour, end up to next hour
        timeline_start = earliest.replace(minute=0, second=0, microsecond=0)
        if earliest.minute != 0 or earliest.second != 0:
            timeline_start = timeline_start
        timeline_end = (latest + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    else:
        # default 08:00 - 17:00
        timeline_start = start_of_week.replace(hour=8, minute=0, second=0, microsecond=0)
        timeline_end = start_of_week.replace(hour=17, minute=0, second=0, microsecond=0)

    # pixels per minute scaling (1 minute -> 1px so 60px per hour; adjust if you want denser)
    PIXELS_PER_MIN = 1

    total_minutes = int((timeline_end - timeline_start).total_seconds() / 60)
    # compute how many all-day rows needed (max over 7 days)
    all_day_rows_per_day = [0]*7
    for i in range(7):
        day_date = (start_of_week + datetime.timedelta(days=i)).date()
        for e in all_day_events:
            # event may span multiple days
            ev_start_date = e['start'].date()
            ev_end_date = (e['end'] - datetime.timedelta(seconds=1)).date()
            if ev_start_date <= day_date <= ev_end_date:
                all_day_rows_per_day[i] += 1
    max_all_day_rows = max(all_day_rows_per_day) if all_day_rows_per_day else 0

    # layout constants
    HEADER_HEIGHT = 20             # px for day header
    ALL_DAY_ROW_HEIGHT = 18        # px per all-day row
    TOP_PADDING = 6                # small gap between all-day area and timed grid

    all_day_area_height = max_all_day_rows * ALL_DAY_ROW_HEIGHT
    timed_area_offset = HEADER_HEIGHT + all_day_area_height + TOP_PADDING

    # Build HTML (the format you provided)
    html_parts = []
    html_parts.append('<!DOCTYPE html>')
    html_parts.append('<html><head><meta charset="utf-8"><title>Kobo Calendar Timetable</title><style>')
    html_parts.append('body {font-family: sans-serif; background:#fff; color:#000; margin:0; padding:0.5em;}')
    html_parts.append('.container {display:flex; width:100%;}')
    html_parts.append('.hour-labels {width:40px; display:flex; flex-direction:column; margin-top:%dpx;}' % timed_area_offset)
    html_parts.append('.hour-labels div {height:60px; font-size:0.7em; text-align:right; padding-right:2px; border-bottom:1px solid #eee;}')
    html_parts.append('.week {display:flex; flex:1;}')
    html_parts.append('.day-column {flex:1; border-left:1px solid #ccc; position:relative; margin-left:2px; min-height:%dpx;}' % (total_minutes * PIXELS_PER_MIN + timed_area_offset + 20))
    html_parts.append('.day-column-header {text-align:center; background:#eee; font-weight:bold; border-bottom:1px solid #ccc; height:%dpx; line-height:%dpx;}' % (HEADER_HEIGHT, HEADER_HEIGHT))
    html_parts.append('.event {position:absolute; left:2px; right:2px; background:#999; color:#fff; font-size:0.7em; padding:1px; border-radius:2px; line-height:1em; overflow:hidden;}')
    html_parts.append('.event .time {font-size:0.65em;}')
    html_parts.append('.event .location {font-size:0.65em;}')
    html_parts.append('.all-day {position:absolute; left:2px; right:2px; background:#555; color:#fff; font-size:0.7em; padding:1px; border-radius:2px; overflow:hidden;}')
    html_parts.append('</style></head><body>')

    html_parts.append('<div class="container">')

    # Hour labels: show each hour between timeline_start and timeline_end
    html_parts.append('<div class="hour-labels">')
    cur = timeline_start
    while cur < timeline_end:
        html_parts.append(f'<div>{cur.hour:02d}:{cur.minute:02d}</div>')
        cur += datetime.timedelta(hours=1)
    html_parts.append('</div>')  # .hour-labels

    # Week columns
    html_parts.append('<div class="week">')

    # precompute all-day layout index per day so stacking is stable
    all_day_indices = [0]*7

    for i in range(7):
        day_date = (start_of_week + datetime.timedelta(days=i)).date()
        html_parts.append(f'<div class="day-column"><div class="day-column-header">{["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][i]} { (start_of_week + datetime.timedelta(days=i)).day }</div>')

        # Render all-day events stacked below header
        idx = 0
        for e in all_day_events:
            ev_start_date = e['start'].date()
            ev_end_date = (e['end'] - datetime.timedelta(seconds=1)).date()
            if ev_start_date <= day_date <= ev_end_date:
                top_px = HEADER_HEIGHT + idx * ALL_DAY_ROW_HEIGHT
                html_parts.append(f'<div class="all-day" style="top:{top_px}px;height:{ALL_DAY_ROW_HEIGHT}px;">{e["summary"]}</div>')
                idx += 1

        # Render timed events for day (possibly spanning multiple days) - positioned relative to timeline_start
        for e in timed_events:
            # event intersects this day?
            ev_start = e['start']
            ev_end = e['end']
            # Convert to date/time and clip to current day/time window
            day_start_dt = datetime.datetime.combine(day_date, datetime.time.min).replace(tzinfo=SG_TZ)
            day_end_dt = datetime.datetime.combine(day_date, datetime.time.max).replace(tzinfo=SG_TZ)

            # intersection between event and this day
            seg_start = max(ev_start, day_start_dt)
            seg_end = min(ev_end, day_end_dt)
            if seg_end <= seg_start:
                continue

            # also intersect with timeline window
            seg_start_tl = max(seg_start, timeline_start)
            seg_end_tl = min(seg_end, timeline_end)
            if seg_end_tl <= seg_start_tl:
                continue

            minutes_from_tl = (seg_start_tl - timeline_start).total_seconds() / 60
            minutes_duration = (seg_end_tl - seg_start_tl).total_seconds() / 60

            top_px = int(timed_area_offset + minutes_from_tl * PIXELS_PER_MIN)
            height_px = max(18, int(minutes_duration * PIXELS_PER_MIN))  # minimum visual height
            # prevent overlapping header by ensuring top_px >= timed_area_offset
            if top_px < timed_area_offset:
                top_px = timed_area_offset

            # safe-escape content (simple)
            summary = e["summary"].replace("<", "&lt;").replace(">", "&gt;")
            location = e["location"].replace("<", "&lt;").replace(">", "&gt;")
            time_str = f'{e["start"].strftime("%H:%M")} - {e["end"].strftime("%H:%M")}'

            html_parts.append(
                f'<div class="event" style="top:{top_px}px;height:{height_px}px;">'
                f'{summary}<br>'
                f'<span class="time">{time_str}</span><br>'
                f'<span class="location">{location}</span>'
                f'</div>'
            )

        html_parts.append('</div>')  # .day-column

    html_parts.append('</div>')  # .week
    html_parts.append('</div>')  # .container
    html_parts.append('</body></html>')

    return "\n".join(html_parts)

# -----------------------------
# Main
# -----------------------------
def main():
    url = os.environ.get("CALENDAR_ICS_URL")
    cal = None
    if not url:
        print("Warning: CALENDAR_ICS_URL not set; generating empty calendar.")
    else:
        try:
            cal = fetch_calendar(url)
        except Exception as e:
            print(f"Error fetching ICS calendar: {e}")
            cal = None

    now = datetime.datetime.now(SG_TZ)
    start_of_week, end_of_week = week_bounds_for(now)

    events = []
    if cal:
        try:
            # Expand recurrences within a reasonable range (week)
            events = parse_events(cal, start_range=start_of_week, end_range=end_of_week)
        except Exception as e:
            print(f"Error parsing events: {e}")
            events = []

    # Filter and clamp to this week
    week_events, start_of_week = filter_week(events, now)

    # Generate HTML
    html = generate_html(week_events, start_of_week)

    # Write calendar.html (overwrite every run)
    try:
        out = "calendar.html"
        print(f"Writing {out} (overwriting if exists)...")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
        print("calendar.html written successfully.")
    except Exception as e:
        print(f"Failed to write calendar.html: {e}")

if __name__ == "__main__":
    main()
