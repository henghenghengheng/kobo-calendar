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
    dt = to_naive_utc(dt)
    days_to_sunday = (dt.weekday() + 1) % 7  # Monday=0 ... Sunday=6
    sunday = dt - datetime.timedelta(days=days_to_sunday)
    return datetime.datetime.combine(sunday.date(), datetime.time(0, 0))

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
    for e in events[:5]:
        print(f"{e['summary']}: {e['start']} → {e['end']}, all_day={e['all_day']}")
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
# HTML generation (visual timetable)
# ------------------------------
def generate_html(events, start_of_week):
    days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
    events_by_day = {i: [] for i in range(7)}
    for e in events:
        weekday = e['start'].weekday()
        events_by_day[weekday].append(e)

    all_day_by_day = {i: [] for i in range(7)}
    timed_by_day = {i: [] for i in range(7)}
    for i in range(7):
        for e in events_by_day[i]:
            if e['all_day']:
                all_day_by_day[i].append(e)
            else:
                timed_by_day[i].append(e)

    # Determine hour range
    min_hour = 24
    max_hour = 0
    for i in range(7):
        for e in timed_by_day[i]:
            min_hour = min(min_hour, e['start'].hour)
            max_hour = max(max_hour, e['end'].hour + 1)
    if min_hour >= max_hour:
        min_hour = 0
        max_hour = 24

    hour_height = 60  # px per hour
    all_day_height = 30

    html = f"""
<html>
<head>
<meta charset='utf-8'>
<title>Weekly Calendar</title>
<style>
body {{font-family: sans-serif; margin:0; padding:0;}}
table {{border-collapse: collapse; width: 100%; table-layout: fixed;}}
th, td {{border: 1px solid #999; vertical-align: top; position: relative; padding:0;}}
.day-header {{height: 40px; text-align: center; background:#eee;}}
.hour-label {{position:absolute; left:0; width:30px; text-align:right; font-size:12px; padding-right:2px;}}
.event {{position:absolute; left:0; right:0; margin:1px; padding:2px; background:#8cf; border:1px solid #38a; font-size:12px; overflow:hidden;}}
.all-day-event {{background:#fc8; border:1px solid #c83; font-size:12px; margin:1px; padding:2px;}}
.td-container {{position:relative; height: {(max_hour-min_hour)*hour_height + all_day_height}px;}}
</style>
</head>
<body>
<table>
<tr>
"""
    # Header row
    for i in range(7):
        day_date = (start_of_week + datetime.timedelta(days=i)).day
        html += f"<th class='day-header'>{days[i]} {day_date}</th>"
    html += "</tr>\n<tr>"

    # Table cells per day
    for i in range(7):
        html += "<td><div class='td-container'>\n"
        # All-day events
        y_offset = 0
        for e in all_day_by_day[i]:
            html += f"<div class='all-day-event' style='top:{y_offset}px;'>{e['summary']}</div>\n"
            y_offset += all_day_height
        # Timed events
        for e in timed_by_day[i]:
            start_offset = ((e['start'].hour + e['start'].minute/60) - min_hour) * hour_height + all_day_height
            end_offset = ((e['end'].hour + e['end'].minute/60) - min_hour) * hour_height + all_day_height
            height = max(end_offset - start_offset, 15)
            html += f"<div class='event' style='top:{start_offset}px; height:{height}px;'>"
            html += f"{e['summary']}<br>{e['start'].strftime('%H:%M')} - {e['end'].strftime('%H:%M')}<br>"
            if e['location']:
                html += f"{e['location']}"
            html += "</div>\n"
        html += "</div></td>"
    html += "</tr>\n</table>\n</body>\n</html>"
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
