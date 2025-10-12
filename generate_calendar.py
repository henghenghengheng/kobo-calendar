import os
import requests
import datetime
from icalendar import Calendar
from dateutil.rrule import rruleset, rrulestr
import pytz

SG_TZ = pytz.timezone("Asia/Singapore")
OUTPUT_FILE = "calendar.html"

# Fetch multiple ICS URLs from secrets
CALENDAR_URLS = [u for u in [
    os.getenv("CALENDAR_ICS_URL"),
    os.getenv("CALENDAR_ICS_URL_1"),
    os.getenv("CALENDAR_ICS_URL_2")
] if u]


def fetch_calendar(url):
    print(f"Fetching calendar: {url}")
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

            exdates = component.get("EXDATE")
            if exdates:
                if not isinstance(exdates, list):
                    exdates = [exdates]
                for ex in exdates:
                    if hasattr(ex, "dts"):
                        for dt in ex.dts:
                            ruleset.exdate(dt.dt)

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


def detect_lanes(events):
    """Assign horizontal lanes to concurrent events per day"""
    by_day = {}
    for e in events:
        d = e["start"].date()
        by_day.setdefault(d, []).append(e)

    for day_events in by_day.values():
        day_events.sort(key=lambda e: e["start"])
        lanes = []
        for e in day_events:
            placed = False
            for lane_idx, lane in enumerate(lanes):
                if e["start"] >= lane[-1]["end"]:
                    lane.append(e)
                    e["lane"] = lane_idx
                    placed = True
                    break
            if not placed:
                e["lane"] = len(lanes)
                lanes.append([e])
        for e in day_events:
            e["lane_count"] = len(lanes)
    return events


def generate_html(events, start_of_week):
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    all_day_events = [e for e in events if e["all_day"]]
    timed_events = [e for e in events if not e["all_day"]]
    timed_events = detect_lanes(timed_events)

    if timed_events:
        earliest_hour = max(0, min(e["start"].hour for e in timed_events) - 1)
        latest_event_end = max(e["end"] for e in timed_events)
        latest_hour = latest_event_end.hour + 1
    else:
        earliest_hour, latest_hour = 8, 17

    PIXELS_PER_MIN = 1
    HEADER_HEIGHT = 30
    ALL_DAY_ROW_HEIGHT = 20
    TOP_PADDING = 4
    timed_area_offset = HEADER_HEIGHT + ALL_DAY_ROW_HEIGHT + TOP_PADDING

    html = []
    html.append("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    html.append("<title>Kobo Calendar Timetable</title>")
    html.append("<style>")
    html.append('body{font-family:"Monaco","Courier New",monospace;background:#fff;color:#000;margin:0;padding:0.5em;}')
    html.append(".container{display:flex;width:100%;}")
    html.append(f".hour-labels{{width:40px;display:flex;flex-direction:column;margin-top:{timed_area_offset}px;}}")
    html.append(".hour-labels div{height:60px;font-size:0.7em;text-align:right;padding-right:2px;border-bottom:1px solid #eee;}")
    html.append(".week{display:flex;flex:1;}")
    html.append(".day-column{flex:1;position:relative;margin-left:2px;}")
    html.append(f".day-column-header{{text-align:center;font-weight:bold;font-size:1em;height:{HEADER_HEIGHT}px;line-height:{HEADER_HEIGHT}px;}}")
    html.append(".event{position:absolute;background:#333;color:#fff;font-size:0.8em;padding:2px;border-radius:3px;line-height:1.2em;overflow:hidden;}")
    html.append(".event .time,.event .location{font-size:0.7em;}")
    html.append(".all-day{position:absolute;left:2px;right:2px;background:#222;color:#fff;font-size:0.75em;padding:1px;border-radius:2px;overflow:hidden;top:30px;height:18px;}")
    html.append("</style>")
    html.append("<script>")
    html.append("""
window.onload = function(){
  let pwd = prompt("Enter password:");
  if(pwd !== "2603"){
    document.body.innerHTML = "<h2>Access denied.</h2>";
  }
};
""")
    html.append("</script></head><body>")
    html.append('<div class="container"><div class="hour-labels">')

    for hr in range(earliest_hour, latest_hour + 1):
        html.append(f"<div>{hr:02d}:00</div>")

    html.append("</div><div class='week'>")

    for i in range(7):
        day_date = (start_of_week + datetime.timedelta(days=i)).date()
        html.append(f'<div class="day-column"><div class="day-column-header">{days[i]} {day_date.day}</div>')

        # All-day
        for e in all_day_events:
            if e["start"].date() <= day_date <= e["end"].date():
                html.append(f'<div class="all-day">{e["summary"]}</div>')

        # Timed events
        for e in timed_events:
            ev_start, ev_end = e["start"], e["end"]
            if ev_start.date() <= day_date <= ev_end.date():
                seg_start = max(ev_start, SG_TZ.localize(datetime.datetime.combine(day_date, datetime.time.min)))
                seg_end = min(ev_end, SG_TZ.localize(datetime.datetime.combine(day_date, datetime.time.max)))
                minutes_from_tl = (seg_start.hour - earliest_hour) * 60 + seg_start.minute
                minutes_duration = (seg_end - seg_start).total_seconds() / 60
                top_px = int(timed_area_offset + minutes_from_tl * PIXELS_PER_MIN)
                height_px = max(20, int(minutes_duration * PIXELS_PER_MIN))
                width_percent = 100 / e["lane_count"]
                left_percent = e["lane"] * width_percent
                html.append(f'<div class="event" style="top:{top_px}px;height:{height_px}px;'
                            f'left:{left_percent}%;width:{width_percent}%;"><b>{e["summary"]}</b><br>'
                            f'<span class="time">{ev_start.strftime("%H:%M")} - {ev_end.strftime("%H:%M")}</span><br>'
                            f'<span class="location">{e["location"]}</span></div>')

        html.append("</div>")
    html.append("</div></div></body></html>")

    return "\n".join(html)


if __name__ == "__main__":
    now = datetime.datetime.now(SG_TZ)
    start_of_week = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + datetime.timedelta(days=7)

    all_events = []
    for url in CALENDAR_URLS:
        ics_text = fetch_calendar(url)
        all_events.extend(parse_events(ics_text, start_of_week, end_of_week))

    all_events.sort(key=lambda e: e["start"])
    html = generate_html(all_events, start_of_week)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Generated {OUTPUT_FILE} with {len(all_events)} events from {len(CALENDAR_URLS)} calendars.")
