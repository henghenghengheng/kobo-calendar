import datetime
import requests
from icalendar import Calendar
import pytz

# -----------------------------
# Local timezone
# -----------------------------
LOCAL_TZ = pytz.timezone("Asia/Singapore")

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
# Parse events
# -----------------------------
def parse_events(cal):
    print("Parsing events...")
    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
            summary = str(component.get("summary"))
            location = str(component.get("location", ""))
            dtstart = component.get("dtstart").dt
            dtend = component.get("dtend").dt
            all_day = False

            # Handle all-day events (date vs datetime)
            if isinstance(dtstart, datetime.date) and not isinstance(dtstart, datetime.datetime):
                all_day = True
                dtstart = datetime.datetime.combine(dtstart, datetime.time.min)
            if isinstance(dtend, datetime.date) and not isinstance(dtend, datetime.datetime):
                all_day = True
                dtend = datetime.datetime.combine(dtend, datetime.time.min)

            # Keep timezone if available
            events.append({
                "summary": summary,
                "location": location,
                "start": dtstart,
                "end": dtend,
                "all_day": all_day
            })
            print(f"{summary}: {dtstart} → {dtend}, all_day={all_day}")
    print(f"Total events parsed: {len(events)}")
    return events

# -----------------------------
# Filter events for the current week (Sunday → Saturday)
# -----------------------------
def filter_week(events, reference_date=None):
    if reference_date is None:
        reference_date = datetime.datetime.now(LOCAL_TZ)
    else:
        if reference_date.tzinfo is None:
            reference_date = LOCAL_TZ.localize(reference_date)

    # Compute start (Sunday) and end (Saturday) of the current week
    weekday = reference_date.weekday()  # Monday=0 ... Sunday=6
    days_to_sunday = (weekday + 1) % 7
    sunday = reference_date - datetime.timedelta(days=days_to_sunday)
    start_of_week = sunday.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + datetime.timedelta(days=6, hours=23, minutes=59, seconds=59)

    week_events = []
    for e in events:
        e_start = e['start']
        e_end = e['end']

        # Make timezone-aware if naive
        if e_start.tzinfo is None:
            e_start = LOCAL_TZ.localize(e_start)
        if e_end.tzinfo is None:
            e_end = LOCAL_TZ.localize(e_end)

        # Include events that overlap the week
        if e_end >= start_of_week and e_start <= end_of_week:
            e_copy = e.copy()
            # Clip events that start before Sunday or end after Saturday
            if e_start < start_of_week:
                e_copy['start'] = start_of_week
            if e_end > end_of_week:
                e_copy['end'] = end_of_week
            week_events.append(e_copy)

    print(f"Events this week: {len(week_events)} (Sunday {start_of_week.date()} → Saturday {end_of_week.date()})")
    for e in week_events:
        print(f"- {e['summary']}: {e['start']} → {e['end']}")
    return week_events, start_of_week

# -----------------------------
# Generate HTML (week view)
# -----------------------------
def generate_html(events, start_of_week):
    days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
    html = ['<html><head><style>']
    html.append('body{font-family:sans-serif;}')
    html.append('.week{display:flex;}')
    html.append('.day{flex:1; border:1px solid #ccc; min-height:500px; position:relative;}')
    html.append('.all_day{background:#f9c74f; margin:2px; padding:2px;}')
    html.append('.event{background:#90be6d; margin:2px; padding:2px; position:absolute;}')
    html.append('.header{background:#f94144; color:white; text-align:center; padding:2px;}')
    html.append('</style></head><body>')
    html.append('<div class="week">')
    for i in range(7):
        day_date = start_of_week + datetime.timedelta(days=i)
        html.append(f'<div class="day"><div class="header">{days[i]} {day_date.day}</div>')

        # all-day events first
        y_offset = 30  # start y for timed events
        for e in events:
            if e['all_day'] and e['start'].date() <= day_date.date() <= e['end'].date():
                html.append(f'<div class="all_day">{e["summary"]}</div>')

        # timed events
        for e in events:
            if not e['all_day'] and e['start'].date() == day_date.date():
                top = e['start'].hour * 30 + e['start'].minute * 0.5 + y_offset
                height = max(20, ((e['end'] - e['start']).seconds / 60) * 0.5)
                html.append(f'<div class="event" style="top:{top}px; height:{height}px;">'
                            f'{e["summary"]}<br>'
                            f'{e["start"].strftime("%H:%M")} - {e["end"].strftime("%H:%M")}<br>'
                            f'{e["location"]}</div>')

        html.append('</div>')
    html.append('</div></body></html>')
    return "\n".join(html)

# -----------------------------
# Main
# -----------------------------
def main():
    import os
    url = os.environ.get("CALENDAR_ICS_URL")
    if not url:
        print("Error: CALENDAR_ICS_URL environment variable not set.")
        return

    cal = fetch_calendar(url)
    events = parse_events(cal)
    week_events, start_of_week = filter_week(events)
    html = generate_html(week_events, start_of_week)

    with open("calendar.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Calendar HTML written to calendar.html")

if __name__ == "__main__":
    main()
