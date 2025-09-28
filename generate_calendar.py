import datetime
import requests
from icalendar import Calendar
import pytz
from dateutil.rrule import rrulestr

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
# Parse events (with weekly recurrence)
# -----------------------------
def parse_events(cal, start_range=None, end_range=None):
    print("Parsing events...")
    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("summary"))
        location = str(component.get("location", ""))
        dtstart = component.get("dtstart").dt
        dtend = component.get("dtend").dt
        all_day = False

        # Handle all-day events
        if isinstance(dtstart, datetime.date) and not isinstance(dtstart, datetime.datetime):
            all_day = True
            dtstart = datetime.datetime.combine(dtstart, datetime.time.min)
        if isinstance(dtend, datetime.date) and not isinstance(dtend, datetime.datetime):
            all_day = True
            dtend = datetime.datetime.combine(dtend, datetime.time.min)

        # Ensure timezone awareness
        if dtstart.tzinfo is None:
            dtstart = dtstart.replace(tzinfo=pytz.UTC)
        if dtend.tzinfo is None:
            dtend = dtend.replace(tzinfo=pytz.UTC)

        # Check for recurrence
        rrule_val = component.get("RRULE")
        if rrule_val:
            rrule_str_full = ";".join([f"{k}={v[0]}" for k, v in rrule_val.items() if str(v[0])])
            rrule_obj = rrulestr(rrule_str_full, dtstart=dtstart)

            # Expand occurrences within the range
            if start_range and end_range:
                occurrences = list(rrule_obj.between(start_range, end_range, inc=True))
            else:
                occurrences = list(rrule_obj)

            for occ_start in occurrences:
                occ_end = occ_start + (dtend - dtstart)
                events.append({
                    "summary": summary,
                    "location": location,
                    "start": occ_start,
                    "end": occ_end,
                    "all_day": all_day
                })
        else:
            events.append({
                "summary": summary,
                "location": location,
                "start": dtstart,
                "end": dtend,
                "all_day": all_day
            })

        print(f"Parsed event: {summary}, start={dtstart}, end={dtend}, all_day={all_day}")

    print(f"Total events parsed: {len(events)}")
    return events

# -----------------------------
# Filter events for the current week (Sunday → Saturday)
# -----------------------------
def filter_week(events, reference_date=None):
    if reference_date is None:
        reference_date = datetime.datetime.now(pytz.timezone("Asia/Singapore"))
    elif reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=pytz.UTC)

    weekday = reference_date.weekday()  # Monday=0 ... Sunday=6
    days_to_sunday = (weekday + 1) % 7
    start_of_week = (reference_date - datetime.timedelta(days=days_to_sunday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_of_week = start_of_week + datetime.timedelta(days=6, hours=23, minutes=59, seconds=59)

    week_events = []
    for e in events:
        e_start, e_end = e['start'], e['end']

        if e_start.tzinfo is None:
            e_start = e_start.replace(tzinfo=pytz.UTC)
        if e_end.tzinfo is None:
            e_end = e_end.replace(tzinfo=pytz.UTC)

        # Check if event overlaps this week
        if e_end >= start_of_week and e_start <= end_of_week:
            e_copy = e.copy()
            if e_start < start_of_week:
                e_copy['start'] = start_of_week
            if e_end > end_of_week:
                e_copy['end'] = end_of_week
            week_events.append(e_copy)

    print(f"Events this week: {len(week_events)} (week {start_of_week.date()} → {end_of_week.date()})")
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

        y_offset = 30

        # All-day events
        for e in events:
            if e['all_day'] and e['start'].date() <= day_date.date() <= e['end'].date():
                html.append(f'<div class="all_day">{e["summary"]}</div>')

        # Timed events
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
    now = datetime.datetime.now(pytz.timezone("Asia/Singapore"))

    # Expand events for this week
    weekday = now.weekday()
    days_to_sunday = (weekday + 1) % 7
    start_of_week = (now - datetime.timedelta(days=days_to_sunday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_of_week = start_of_week + datetime.timedelta(days=6, hours=23, minutes=59, seconds=59)

    events = parse_events(cal, start_of_week, end_of_week)
    week_events, start_of_week = filter_week(events, now)
    html = generate_html(week_events, start_of_week)

    with open("calendar.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Calendar HTML written to calendar.html")

if __name__ == "__main__":
    main()
