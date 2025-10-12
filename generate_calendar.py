import os
import requests
import datetime
from icalendar import Calendar, Event
from dateutil.rrule import rruleset, rrulestr
import pytz

SG_TZ = pytz.timezone("Asia/Singapore")
CALENDAR_URL = os.getenv("CALENDAR_ICS_URL")
OUTPUT_FILE = "calendar.html"


def fetch_calendar(url):
    print("Fetching calendar...")
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text


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
            start = SG_TZ.localize(datetime.datetime.combine(dtstart, datetime.time.min))
            end = SG_TZ.localize(datetime.datetime.combine(dtend, datetime.time.min))
            all_day = True
        else:
            if dtstart.tzinfo is None:
                dtstart = SG_TZ.localize(dtstart)
            else:
                dtstart = dtstart.astimezone(SG_TZ)
            if dtend.tzinfo is None:
                dtend = SG_TZ.localize(dtend)
            else:
                dtend = dtend.astimezone(SG_TZ)
            start, end, all_day = dtstart, dtend, False

        if component.get("RRULE"):
            ruleset = rruleset()
            rrule_str = component.get("RRULE").to_ical().decode()
            rrule = rrulestr(rrule_str, dtstart=start)
            ruleset.rrule(rrule)

            # --- FIXED handling of RDATE and EXDATE ---
            rdates = component.get("RDATE")
            if rdates:
                if not isinstance(rdates, list):
                    rdates = [rdates]
                for r in rdates:
                    if hasattr(r, "dts"):
                        for dt in r.dts:
                            ruleset.rdate(dt.dt)

            exdates = component.get("EXDATE")
            if exdates:
                if not isinstance(exdates, list):
                    exdates = [exdates]
                for ex in exdates:
                    if hasattr(ex, "dts"):
                        for dt in ex.dts:
                            ruleset.exdate(dt.dt)
            # -------------------------------------------

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
            if end >= start_of_week and start <= end_of_week:
                events.append({
                    "summary": summary,
                    "location": location,
                    "start": start,
                    "end": end,
                    "all_day": all_day
                })

    return events


def generate_html(events, start_of_week):
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    all_day_events = [e for e in events if e["all_day"]]
    timed_events = [e for e in events if not e["all_day"]]

    if timed_events:
        earliest_hour = max(0, min(e["start"].hour for e in timed_events) - 1)
        latest_hour = min(23, max(e["end"].hour for e in timed_events) + 1)
    else:
        earliest_hour, latest_hour = 8, 17

    PIXELS_PER_MIN = 1
    HEADER_HEIGHT = 20
    ALL_DAY_ROW_HEIGHT = 18
    TOP_PADDING = 6

    all_day_rows_per_day = [0] * 7
    for i in range(7):
        day_date = (start_of_week + datetime.timedelta(days=i)).date()
        for e in all_day_events:
            if e["start"].date() <= day_date <= e["end"].date():
                all_day_rows_per_day[i] += 1
    max_all_day_rows = max(all_day_rows_per_day) if all_day_rows_per_day else 0
    all_day_area_height = max_all_day_rows * ALL_DAY_ROW_HEIGHT
    timed_area_offset = HEADER_HEIGHT + all_day_area_height + TOP_PADDING

    total_minutes = (latest_hour - earliest_hour + 1) * 60

    html = []
    html.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    html.append("<title>Kobo Calendar Timetable</title>")
    html.append("<style>")
    html.append('body{font-family:"Courier New",monospace;background:#fff;color:#000;margin:0;padding:0.5em;}')
    html.append(".container{display:flex;width:100%;}")
    html.append(f".hour-labels{{width:40px;display:flex;flex-direction:column;margin-top:{timed_area_offset}px;}}")
    html.append(".hour-labels div{height:60px;font-size:0.7em;text-align:right;padding-right:2px;border-bottom:1px solid #eee;}")
    html.append(".week{display:flex;flex:1;}")
    html.append(f".day-column{{flex:1;border-left:1px solid #ccc;position:relative;margin-left:2px;min-height:{total_minutes*PIXELS_PER_MIN + timed_area_offset + 20}px;}}")
    html.append(f".day-column-header{{text-align:center;background:#eee;font-weight:bold;border-bottom:1px solid #ccc;height:{HEADER_HEIGHT}px;line-height:{HEADER_HEIGHT}px;}}")
    html.append(".event{position:absolute;left:2px;right:2px;background:#999;color:#fff;font-size:0.7em;padding:1px;border-radius:2px;line-height:1em;overflow:hidden;}")
    html.append(".event .time,.event .location{font-size:0.65em;}")
    html.append(".all-day{position:absolute;left:2px;right:2px;background:#555;color:#fff;font-size:0.7em;padding:1px;border-radius:2px;overflow:hidden;}")
    html.append("</style></head><body>")

    html.append('<div class="container">')
    html.append('<div class="hour-labels">')
    for hr in range(earliest_hour, latest_hour + 1):
        html.append(f"<div>{hr:02d}:00</div>")
    html.append("</div>")
    html.append('<div class="week">')

    for i in range(7):
        day_date = (start_of_week + datetime.timedelta(days=i)).date()
        html.append(f'<div class="day-column"><div class="day-column-header">{days[i]} {day_date.day}</div>')
        idx = 0
        for e in all_day_events:
            if e["start"].date() <= day_date <= e["end"].date():
                top_px = HEADER_HEIGHT + idx * ALL_DAY_ROW_HEIGHT
                html.append(f'<div class="all-day" style="top:{top_px}px;height:{ALL_DAY_ROW_HEIGHT}px;">{e["summary"]}</div>')
                idx += 1

        for e in timed_events:
            ev_start, ev_end = e["start"], e["end"]
            if ev_start.date() <= day_date <= ev_end.date():
                seg_start = max(ev_start, SG_TZ.localize(datetime.datetime.combine(day_date, datetime.time.min)))
                seg_end = min(ev_end, SG_TZ.localize(datetime.datetime.combine(day_date, datetime.time.max)))
                minutes_from_tl = (seg_start.hour - earliest_hour) * 60 + seg_start.minute
                minutes_duration = (seg_end - seg_start).total_seconds() / 60
                top_px = int(timed_area_offset + minutes_from_tl * PIXELS_PER_MIN)
                height_px = max(18, int(minutes_duration * PIXELS_PER_MIN))
                html.append(f'<div class="event" style="top:{top_px}px;height:{height_px}px;">{e["summary"]}<br>'
                            f'<span class="time">{ev_start.strftime("%H:%M")} - {ev_end.strftime("%H:%M")}</span><br>'
                            f'<span class="location">{e["location"]}</span></div>')

        html.append("</div>")
    html.append("</div></div></body></html>")

    return "\n".join(html)


if __name__ == "__main__":
    now = datetime.datetime.now(SG_TZ)
    start_of_week = now - datetime.timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + datetime.timedelta(days=7)

    ics_text = fetch_calendar(CALENDAR_URL)
    events = parse_events(ics_text, start_of_week, end_of_week)
    events.sort(key=lambda e: e["start"])

    html = generate_html(events, start_of_week)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Generated {OUTPUT_FILE} with {len(events)} events.")
