import os
import datetime
import requests
import pytz
from icalendar import Calendar

# ------------------------------
# Configuration
# ------------------------------
CALENDAR_ICS_URL = os.environ.get("CALENDAR_ICS_URL")  # Your Google Calendar ICS URL
DAYS_AHEAD = 7
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

def get_start_of_week(dt):
    return dt - datetime.timedelta(days=dt.weekday()+1 if dt.weekday() != 6 else 0)

def to_naive_utc(dt):
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is not None:
            return dt.astimezone(pytz.UTC).replace(tzinfo=None)
        else:
            return dt
    return datetime.datetime.combine(dt, datetime.time())

def parse_events(cal):
    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
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
    start_of_week = get_start_of_week(reference_date)
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
    return week_events, start_of_week

# (Include generate_html function from your previous version here)

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
