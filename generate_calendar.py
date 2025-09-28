#!/usr/bin/env python3
# generate_calendar.py
# Requires: requests, icalendar
import os
import sys
import html
from datetime import datetime, timezone
import requests
from icalendar import Calendar

CALENDAR_ICS_URL = os.environ.get("CALENDAR_ICS_URL")
OUTFILE = os.environ.get("OUTFILE", "calendar.html")
MAX_EVENTS = int(os.environ.get("MAX_EVENTS", "50"))

if not CALENDAR_ICS_URL:
    print("Error: CALENDAR_ICS_URL environment variable not set.", file=sys.stderr)
    sys.exit(1)

def fetch_ics(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.content

def parse_events(ics_bytes):
    cal = Calendar.from_ical(ics_bytes)
    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
            start = component.get('dtstart')
            end = component.get('dtend')
            summary = str(component.get('summary') or "")
            desc = str(component.get('description') or "")
            loc = str(component.get('location') or "")
            # .dt may be date or datetime
            sdt = start.dt if start is not None else None
            edt = end.dt if end is not None else None
            events.append({"start": sdt, "end": edt, "summary": summary, "description": desc, "location": loc})
    # sort safe: put events without times at end
    def keyfn(e):
        if e["start"] is None: 
            return datetime.max.replace(tzinfo=timezone.utc)
        return e["start"]
    events.sort(key=keyfn)
    return events

def fmt_dt(dt):
    if dt is None: return ""
    if isinstance(dt, datetime):
        # convert to localish ISO-like string (UTC-normalized)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M")
    else:
        # date object
        return dt.strftime("%Y-%m-%d")

def build_html(events):
    head = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=420">
<title>My Calendar</title>
<style>
  body{ font-family: -apple-system, "Helvetica Neue", Arial; padding:10px; max-width:420px; }
  h1{ font-size:18px; margin:0 0 8px 0; }
  .event{ padding:8px 6px; border-bottom:1px solid #ddd; }
  .time{ font-size:12px; color:#444; }
  .title{ font-size:15px; margin-top:4px; }
  .desc{ font-size:12px; color:#333; margin-top:6px; white-space:pre-wrap; }
  .muted{ color:#666; font-size:12px; }
</style>
</head>
<body>
<h1>Upcoming</h1>
<div id="events">
"""
    body = ""
    if not events:
        body += "<p class='muted'>No events found.</p>\n"
    else:
        for e in events[:MAX_EVENTS]:
            s = html.escape(fmt_dt(e["start"]))
            en = html.escape(fmt_dt(e["end"]))
            title = html.escape(e["summary"] or "(No title)")
            desc = html.escape(e["description"] or "")
            loc = html.escape(e["location"] or "")
            meta = s + ((" → " + en) if en else "")
            body += f"<div class='event'><div class='time'>{meta}</div><div class='title'>{title}</div>"
            extras = ""
            if loc:
                extras += f"\nLocation: {loc}"
            if desc:
                extras += ("\n\n" if extras else "\n") + desc
            if extras:
                body += f"<div class='desc'>{html.escape(extras)}</div>"
            body += "</div>\n"
    foot = """
</div>
<!-- refresh every 6 hours when opened (optional) -->
<meta http-equiv="refresh" content="21600">
</body>
</html>
"""
    return head + body + foot

def main():
    try:
        ics = fetch_ics(CALENDAR_ICS_URL)
    except Exception as e:
        print("Failed to fetch ICS:", e, file=sys.stderr)
        sys.exit(1)

    events = parse_events(ics)
    html_out = build_html(events)
    with open(OUTFILE, "w", encoding="utf-8") as f:
        f.write(html_out)
    print("Wrote", OUTFILE)

if __name__ == "__main__":
    main()
