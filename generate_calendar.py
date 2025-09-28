import datetime
import requests
from icalendar import Calendar
import pytz
from dateutil.rrule import rrulestr
import re

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
            # Remove unsupported numeric-only tokens
            rrule_str_clean = re.sub(r'(?:^|;)\d+=\d+', '', rrule_str_full)

            try:
                rrule_obj = rrulestr(rrule_str_clean, dtstart=dtstart)
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
            except Exception as e:
                print(f"Warning: Skipping unsupported RRULE for event '{summary}': {e}")
                events.append({
                    "summary": summary,
                    "location": location,
                    "start": dtstart,
                    "end": dtend,
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
# Generate HTML timetable
# -----------------------------
def generate_html(events, start_of_week):
    days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

    html = ['<!DOCTYPE html>']
    html.append('<html>')
    html.append('<head>')
    html.append('<meta charset="utf-8">')
    html.append('<title>Kobo Calendar Timetable</title>')
    html.append('<style>')
    html.append('body { font-family: sans-serif; background: #fff; color: #000; margin: 0; padding: 0.5em; }')
    html.append('.container { display: flex; width: 100%; }')
    html.append('.hour-labels { width: 40px; display: flex; flex-direction: column; margin-top: 40px; }')
    html.append('.hour-labels div { height: 60px; font-size: 0.7em; text-align: right; padding-right: 2px; border-bottom: 1px solid #eee; }')
    html.append('.week { display: flex; flex: 1; }')
    html.append('.day-column { flex: 1; border-left: 1px solid #ccc; position: relative; margin-left: 2px; }')
    html.append('.day-column-header { text-align: center; background: #eee; font-weight: bold; border-bottom: 1px solid #ccc; height: 20px; line-height: 20px; }')
    html.append('.event { position: absolute; left: 2px; right: 2px; background: #999; color: #fff; font-size: 0.7em; padding: 1px; border-radius: 2px; line-height: 1em; }')
    html.append('.event .time { font-size: 0.65em; }')
    html.append('.event .location { font-size: 0.65em; }')
    html.append('.all-day { position: absolute; left: 2px; right: 2px; top: 20px; background: #555; color: #fff; font-size: 0.7em; padding: 1px; border-radius: 2px; }')
    html.append('</style>')
    html.append('</head>')
    html.append('<body>')
    html.append('<div class="container">')

    # Hours column
    html.append('<div class="hour-labels">')
    for hour in range(8, 18):  # 08:00 to 17:00
        html.append(f'<div>{hour:02d}:00</div>')
    html.append('</div>')

    # Week columns
    html.append('<div class="week">')
    for i in range(7):
        day_date = start_of_week + datetime.timedelta(days=i)
        html.append(f'<div class="day-column">')
        html.append(f'<div class="day-column-header">{days[i]} {day_date.day}</div>')

        # All-day events
        for e in events:
            if e['all_day'] and e['start'].date() <= day_date.date() <= e['end'].date():
                html.append(f'<div class="all-day">{e["summary"]}</div>')

        # Timed events
        for e in events:
            if not e['all_day'] and e['start'].date() == day_date.date():
                top = ((e['start'].hour + e['start'].minute / 60) - 8) * 60 + 20  # 20px offset for header
                height = max(20, ((e['end'] - e['start']).seconds / 3600) * 60)
                html.append(f'<div class="event" style="top:{top}px; height:{height}px;">')
                html.append(f'{e["summary"]}<br>')
                html.append(f'<span class="time">{e["start"].strftime("%H:%M")} - {e["end"].strftime("%H:%M")}</span><br>')
                if e["location"]:
                    html.append(f'<span class="location">{e["location"]}</span>')
                html.append('</div>')

        html.append('</div>')
    html.append('</div>')  # end of week
    html.append('</div>')  # end of container
    html.append('</body></html>')

    return "\n".join(html)

# -----------------------------
# Main
# -----------------------------
def main():
    import os
    url = os.environ.get("CALENDAR_ICS_URL")
    cal = None
    if url:
        try:
            cal = fetch_calendar(url)
        except Exception as e:
            print(f"Error fetching ICS calendar: {e}")

    now = datetime.datetime.now(pytz.timezone("Asia/Singapore"))
    events = []
    if cal:
        try:
            events = parse_events(cal)
        except Exception as e:
            print(f"Error parsing events: {e}")

    try:
        week_events, start_of_week = filter_week(events, now)
    except Exception as e:
        print(f"Error filtering week events: {e}")
        week_events, start_of_week = [], now

    try:
        html = generate_html(week_events, start_of_week)
    except Exception as e:
        print(f"Error generating HTML: {e}")
        html = "<html><body><h1>Error generating calendar</h1></body></html>"

    try:
        fpath = "calendar.html"
        print(f"Writing calendar.html to {fpath} ...")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(html)
        print("Calendar HTML written successfully")
    except Exception as e:
        print(f"Error writing calendar.html: {e}")

if __name__ == "__main__":
    main()
