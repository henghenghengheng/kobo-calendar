import os
import requests
from icalendar import Calendar
from datetime import datetime, date, time, timedelta, timezone
from dateutil.rrule import rrulestr

OUTPUT_FILE = "index.html"  # GitHub Pages root

def fetch_ics(url: str) -> Calendar:
    resp = requests.get(url)
    resp.raise_for_status()
    return Calendar.from_ical(resp.text)

def normalize_dt(dt):
    """Return a naive UTC datetime, or None if invalid."""
    if not dt:
        return None
    if hasattr(dt, "dt"):
        dt = dt.dt
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    elif isinstance(dt, date):
        return datetime.combine(dt, time.min)
    return None

def get_current_week_range():
    """Return start (Sunday 00:00) and end (Saturday 23:59) of this week."""
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    days_since_sunday = (today.weekday() + 1) % 7
    start_of_week = today - timedelta(days=days_since_sunday)
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return start_of_week, end_of_week

def parse_events(cal: Calendar):
    events = []
    week_start, week_end = get_current_week_range()

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        start = normalize_dt(component.get("DTSTART"))
        end = normalize_dt(component.get("DTEND"))
        summary = str(component.get("SUMMARY", "No Title"))
        rrule_data = component.get("RRULE")

        # skip invalid events
        if not start or not end:
            continue

        # handle recurrence
        if rrule_data:
            rrule_str_full = ""
            for k, v in rrule_data.items():
                rrule_str_full += f"{k}={','.join(map(str,v))};"
            rrule_str_full = rrule_str_full.rstrip(";")
            try:
                rule = rrulestr(rrule_str_full, dtstart=start)
                for occ in rule.between(week_start, week_end, inc=True):
                    occ_end = occ + (end - start)
                    events.append({
                        "start": occ,
                        "end": occ_end,
                        "summary": summary,
                    })
            except Exception as e:
                print(f"Skipping recurring event '{summary}' due to parsing error: {e}")
        else:
            if week_start <= start <= week_end:
                events.append({
                    "start": start,
                    "end": end,
                    "summary": summary,
                })

    events.sort(key=lambda e: e["start"])
    return events

def render_html(events):
    html = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='utf-8'>",
        "<title>Kobo Calendar</title>",
        "<style>",
        "body { font-family: sans-serif; background: #fff; color: #000; padding: 1em; }",
        "h1 { font-size: 1.4em; margin-bottom: 0.5em; }",
        "div.event { margin-bottom: 1em; padding-bottom: 0.5em; border-bottom: 1px solid #ccc; }",
        "div.date { font-weight: bold; margin-bottom: 0.2em; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Events This Week</h1>"
    ]

    if not events:
        html.append("<p>No events scheduled this week.</p>")
    else:
        for e in events:
            date_str = e["start"].strftime("%a, %b %d %Y")
            if e["start"].time() != time.min or e["end"].time() != time.min:
                time_str = f"{e['start'].strftime('%H:%M')} – {e['end'].strftime('%H:%M')}"
            else:
                time_str = "All day"
            html.append("<div class='event'>")
            html.append(f"<div class='date'>{date_str} ({time_str})</div>")
            html.append(f"<div class='summary'>{e['summary']}</div>")
            html.append("</div>")

    html.extend(["</body>", "</html>"])
    return "\n".join(html)

def main():
    url = os.environ.get("CALENDAR_ICS_URL")
    if not url:
        raise RuntimeError("CALENDAR_ICS_URL environment variable not set.")

    cal = fetch_ics(url)
    events = parse_events(cal)
    html = render_html(events)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Wrote {len(events)} events to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
