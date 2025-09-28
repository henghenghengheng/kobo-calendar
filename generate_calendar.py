import os
import requests
from icalendar import Calendar
from datetime import datetime, date, time, timedelta

OUTPUT_FILE = "calendar.html"

def fetch_ics(url: str) -> Calendar:
    resp = requests.get(url)
    resp.raise_for_status()
    return Calendar.from_ical(resp.text)

def normalize_dt(dt):
    """Ensure we always return a datetime (never a date)."""
    if hasattr(dt, "dt"):
        dt = dt.dt
    if isinstance(dt, datetime):
        return dt
    elif isinstance(dt, date):
        return datetime.combine(dt, time.min)
    return None

def parse_events(cal: Calendar, days_ahead: int = 14):
    events = []
    now = datetime.utcnow()
    cutoff = now + timedelta(days=days_ahead)

    for component in cal.walk():
        if component.name == "VEVENT":
            start = normalize_dt(component.get("DTSTART"))
            end = normalize_dt(component.get("DTEND"))
            summary = str(component.get("SUMMARY", "No Title"))
            if start and start <= cutoff and end:
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
        "<h1>Upcoming Events</h1>"
    ]

    if not events:
        html.append("<p>No events found.</p>")
    else:
        for e in events:
            date_str = e["start"].strftime("%a, %b %d %Y")
            if e["start"].time() != time.min or e["end"].time() != time.min:
                # timed event
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
    events = parse_events(cal, days_ahead=14)
    html = render_html(events)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(htm
