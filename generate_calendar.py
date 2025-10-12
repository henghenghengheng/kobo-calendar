import os
import requests
import datetime
from icalendar import Calendar, Event
from dateutil.rrule import rruleset, rrulestr
import pytz

# === CONFIGURATION ===
SG_TZ = pytz.timezone("Asia/Singapore")
CALENDAR_URL = os.getenv("CALENDAR_ICS_URL")
OUTPUT_FILE = "calendar.html"


# === FETCH ICS FILE ===
def fetch_calendar(url):
    print("Fetching calendar...")
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text


# === PARSE EVENTS (INCLUDING RECURRING) ===
def parse_events(ics_text, start_of_week, end_of_week):
    cal = Calendar.from_ical(ics_text)
    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("SUMMARY", ""))
        location = str(component.get("LOCATION", ""))
        dtstart = component.get("DTSTART").dt
        dtend = component.get("DTEND").dt

        if isinstance(dtstart, datetime.date) and not isinstance(dtstart, datetime.datetime):
            # all-day event
            start = SG_TZ.localize(datetime.datetime.combine(dtstart, datetime.time.min))
            end = SG_TZ.localize(datetime.datetime.combine(dtend, datetime.time.min))
            all_day = True
        else:
            # timed event
            if dtstart.tzinfo is None:
                dtstart = SG_TZ.localize(dtstart)
            else:
                dtstart = dtstart.astimezone(SG_TZ)
            if dtend.tzinfo is None:
                dtend = SG_TZ.localize(dtend)
            else:
                dtend = dtend.astimezone(SG_TZ)
            start = dtstart
            end = dtend
            all_day = False

        # Handle recurrence rules
        if component.get("RRULE"):
            ruleset = rruleset()
            rrule_str = component.get("RRULE").to_ical().decode()
            rrule = rrulestr(rrule_str, dtstart=start)
            ruleset.rrule(rrule)

            for rdate in component.get("RDATE", []):
                ruleset.rdate(rdate.dt)
            for exdate in component.get("EXDATE", []):
                ruleset.exdate(exdate.dt)

            for occur in ruleset.between(start_of_week, end_of_week, inc=True):
                ev_start = occur
                ev_end = ev_start + (end - start)
                events.append({
                    "summary": summary,
                    "location": location,
                    "start": ev_start,
                    "end": ev_end,
                    "all_day": all_day
                })
        else:
            # Non-recurring
            if end >= start_of_week and start <= end_of_week:
                events.append({
                    "summary": summary,
                    "location": location,
                    "start": start,
                    "end": end,
                    "all_day": all_day
                })

    return events


# === GENERATE HTML ===
def generate_html(events, start_of_week):
    import math

    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    all_day_events = [e for e in events if e["all_day"]]
    timed_events = [e for e in events if not e["all_day"]]

    # Determine daily hour range
    if timed_events:
        earliest_hour = min(e["start"].hour for e in timed_events)
        latest_hour = max(e["end"].hour for e in timed_events)
        earliest_hour = max(0, earliest_hour - 1)
        latest_hour = min(23, latest_hour + 1)
    else:
        earliest_hour, latest_hour = 8, 17

    timeline_start = start_of_week.replace(hour=earliest_hour, minute=0, second=0, microsecond=0)
    timeline_end = start_of_week.replace(hour=latest_hour, minute=0, second=0, microsecond=0)
    PIXELS_PER_MIN = 1
    total_minutes = int((timeline_end - timeline_start).total_seconds() / 60)

    # All-day stacking
    all_day_rows_per_day = [0] * 7
    for i in range(7):
        day_date = (start_of_week + datetime.timedelta(days=i)).date()
        for e in all_day_events:
            ev_start_date = e["start"].date()
            ev_end_date = (e["end"] - datetime.timedelta(seconds=1)).date()
            if ev_start_date <= day_date <= ev_end_date:
                all_day_rows_per_day[i] += 1
    max_all_day_rows = max(all_day_rows_per_day) if all_day_rows_per_day else 0

    HEADER_HEIGHT = 20
    ALL_DAY_ROW_HEIGHT = 18
    TOP_PADDING = 6
    all_day_area_height = max_all_day_rows * ALL_DAY_ROW_HEIGHT
    timed_area_offset = HEADER_HEIGHT + all_day_area_height + TOP_PADDING

    html = []
    html.append("<!DOCTYPE html>")
    html.append("<html><head><meta charset='utf-8'><title>Kobo Calendar Timetable</title><style>")
    html.append('body {font-family:"Courier New",monospace;background:#fff;color:#000;margin:0;padding:0.5em;}')
    html.append(".container {display:flex;width:100%;}")
    html.append(f".hour-labels {{width:40px;display:flex;flex-direction:column;margin-top:{timed_area_offset}px;}}")
    html.append(".hour-labels div {height:60px;font-size:0.7em;text-align:right;padding-right:2px;border-bottom:1px solid #eee;}")
    html.append(".week {display:flex;flex:1;}")
    html.append(f".day-column {{flex:1;border-left:1px solid #ccc;position:relative;margin-left:2px;min-height:{total_minutes*PIXELS_PER_MIN + timed_area_offset + 20}px;}}")
    html.append(f".day-column-header {{text-align:center;background:#eee;font-weight:bold;border-bottom:1px solid #ccc;height:{HEADER_HEIGHT}px;line-height:{HEADER_HEIGHT}px;}}")
    html.append(".event {position:absolute;left:2px;right:2px;background:#999;color:#fff;font-size:0.7em;padding:1px;border-radius:2px;line-height:1em;overflow:hidden;}")
    html.append(".event .time, .event .location {font-size:0.65em;}")
    html.append(".all-day {position:absolute;left:2px;right:2px;background:#555;color:#fff;font-size:0.7em;padding:1px;border-radius:2px;overflow:hidden;}")
    html.append("</style></head><body>")

    html.append('<div class="container">')

    # Hour labels
    html.append('<div class="hour-labels">')
    cur = timeline_start
    while cur < timeline_end:
        html.append(f"<div>{cur.hour:02d}:00</div>")
        cur += datetime.timedelta(hours=1)
    html.append("</div>")

    # Week columns
    html.append('<div class="week">')

    for i in range(7):
        day_date = (start_of_week + datetime.timedelta(days=i)).date()
        html.append(f'<div class="day-column"><div class="day-column-header">{days[i]} {day_date.day}</div>')

        # All-day events
        idx = 0
        for e in all_day_events:
            ev_start_date = e["start"].date()
            ev_end_date = (e["end"] - datetime.timedelta(seconds=1)).date()
            if ev_start_date <= day_date <= ev_end_date:
                top_px = HEADER_HEIGHT + idx * ALL_DAY_ROW_HEIGHT
                html.append(f'<div class="all-day" style="top:{top_px}px;height:{ALL_DAY_ROW_HEIGHT}px;">{e["summary"]}</div>')
                idx += 1

        # Timed events
        for e in timed_events:
            ev_start = e["start"]
            ev_end = e["end"]
            day_start_dt = SG_TZ.localize(datetime.datetime.combine(day_date, datetime.time.min))
            day_end_dt = SG_TZ.localize(datetime.datetime.combine(day_date, datetime.time.max))
            seg_start = max(ev_start, day_start_dt)
            seg_end = min(ev_end, day_end_dt)
            if seg_end <= seg_start:
                continue

            minutes_from_tl = (seg_start.hour - earliest_hour) * 60 + seg_start.minute
            minutes_duration = (seg_end - seg_start).total_seconds() / 60
            top_px = int(timed_area_offset + minutes_from_tl * PIXELS_PER_MIN)
            height_px = max(18, int(minutes_duration * PIXELS_PER_MIN))

            summary = e["summary"].replace("<", "&lt;").replace(">", "&gt;")
            location = e["location"].replace("<", "&lt;").replace(">", "&gt;")
            time_str = f'{e["start"].strftime("%H:%M")} - {e["end"].strftime("%H:%M")}'

            html.append(
                f'<div class="event" style="top:{top_px}px;height:{height_px}px;">'
                f'{summary}<br><span class="time">{time_str}</span><br><span class="location">{location}</span>'
                f'</div>'
            )

        html.append("</div>")

    html.append("</div></div></body></html>")
    return "\n".join(html)


# === MAIN ===
if __name__ == "__main__":
    now = datetime.datetime.now(SG_TZ)
    start_of_week = now - datetime.timedelta(days=now.weekday())  # Monday start
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + datetime.timedelta(days=7)

    ics_text = fetch_calendar(CALENDAR_URL)
    events = parse_events(ics_text, start_of_week, end_of_week)
    events.sort(key=lambda e: e["start"])

    html = generate_html(events, start_of_week)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Generated {OUTPUT_FILE} with {len(events)} events.")
