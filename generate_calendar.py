import os
import datetime
import requests
import pytz
from icalendar import Calendar

# ------------------------------
# Configuration
# ------------------------------
CALENDAR_ICS_URL = os.environ.get("CALENDAR_ICS_URL")  # Google Calendar ICS URL
OUTPUT_HTML = "calendar.html"
HOUR_HEIGHT_PX = 60
ALL_DAY_HEIGHT_PX = 20
HEADER_HEIGHT_PX = 20

# ------------------------------
# Helper functions
# ------------------------------
def fetch_ics(url):
    response = requests.get(url)
    print("ICS fetch status code:", response.status_code)
    response.raise_for_status()
    return Calendar.from_ical(response.text)

def to_naive_utc(dt):
    """Convert datetime or date to naive UTC datetime"""
    if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        dt = datetime.datetime.combine(dt, datetime.time())
    if dt.tzinfo is not None:
        dt = dt.astimezone(pytz.UTC).replace(tzinfo=None)
    return dt

def get_sunday_start(dt):
    """Get Sunday at 00:00:00 of the current week"""
    weekday = dt.weekday()  # Monday=0 ... Sunday=6
    days_to_sunday = (weekday + 1) % 7
    sunday = dt - datetime.timedelta(days=days_to_sunday)
    return datetime.datetime.combine(sunday.date(), datetime.time())

def parse_events(cal):
    events = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        start_prop = component.get('dtstart')
        end_prop = component.get('dtend')

        if start_prop is None:
            continue

        start = start_prop.dt
        end = end_prop.dt if end_prop else start + datetime.timedelta(hours=1)

        all_day = False
        if isinstance(start, datetime.date) and not isinstance(start, datetime.datetime):
            start = datetime.datetime.combine(start, datetime.time())
            end = datetime.datetime.combine(end, datetime.time())
            all_day = True

        start = to_naive_utc(start)
        end = to_naive_utc(end)

        location = component.get('location')
        events.append({
            'summary': str(component.get('summary', 'No Title')),
            'start': start,
            'end': end,
            'all_day': all_day,
            'location': str(location) if location else ''
        })

    print(f"Total events parsed: {len(events)}")
    return events

def filter_week(events, reference_date=None):
    if reference_date is None:
        reference_date = datetime.datetime.utcnow()
    reference_date = to_naive_utc(reference_date)
    start_of_week = get_sunday_start(reference_date)
    end_of_week = start_of_week + datetime.timedelta(days=7)

    week_events = []
    for e in events:
        if e['end'] > start_of_week and e['start'] < end_of_week:
            e_copy = e.copy()
            if e_copy['start'] < start_of_week:
                e_copy['start'] = start_of_week
            if e_copy['end'] > end_of_week:
                e_copy['end'] = end_of_week
            week_events.append(e_copy)

    print(f"Events this week: {len(week_events)} (week starting {start_of_week.date()})")
    for e in week_events:
        print(f"- {e['summary']}: {e['start']} → {e['end']}")
    return week_events, start_of_week

# ------------------------------
# HTML generation
# ------------------------------
def generate_html(events, start_of_week):
    # Minimal HTML for testing, you can replace with your styled timetable
    html = "<html><head><meta charset='utf-8'><title>Weekly Calendar</title></head><body>\n"
    html += f"<h2>Week starting {start_of_week.date()}</h2>\n"
    for e in events:
        html += f"<div style='border:1px solid black; margin:5px; padding:5px;'>"
        html += f"<strong>{e['summary']}</strong><br>"
        html += f"{e['start'].strftime('%H:%M')} - {e['end'].strftime('%H:%M')}<br>"
        if e['location']:
            html += f"{e['location']}<br>"
        html += "</div>\n"
    html += "</body></html>"
    return html

# ------------------------------
# Main
# ------------------------------
def main():
    if not CALENDAR_ICS_URL:
        raise ValueError("CALENDAR_ICS_URL environment variable not set")

    print("Fetching ICS calendar...")
    cal = fetch_ics(CALENDAR_ICS_URL)

    print("Parsing events...")
    events = parse_events(cal)

    print("Filtering events for this week...")
    week_events, start_of_week = filter_week(events)

    print("Generating HTML...")
    html = generate_html(week_events, start_of_week)

    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Calendar HTML written to {OUTPUT_HTML}")

if __name__ == "__main__":
    main()
