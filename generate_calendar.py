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
    print(f"Fetching calendar: {url} ...")
    r = requests.get(url)
    print(f"ICS fetch status code: {r.status_code}")
    r.raise_for_status()
    return Calendar.from_ical(r.text)

# -----------------------------
# Parse events (including recurrence)
# -----------------------------
def parse_events(cal, start_range=None, end_range=None):
    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("summary"))
        dtstart = component.get("dtstart").dt
        dtend = component.get("dtend")
        if dtend is not None:
            dtend = dtend.dt
        else:
            # Fallback: 1 hour event if DTEND missing
            dtend = dtstart + datetime.timedelta(hours=1)
        all_day = False

        # Handle all-day events
        if isinstance(dtstart, datetime.date) and not isinstance(dtstart, datetime.datetime):
            all_day = True
            dtstart = datetime.datetime.combine(dtstart, datetime.time.min)
        if isinstance(dtend, datetime.date) and not isinstance(dtend, datetime.datetime):
            all_day = True
            dtend = datetime.datetime.combine(dtend, datetime.time.min)

        # Ensure timezone aware
        if dtstart.tzinfo is None:
            dtstart = dtstart.replace(tzinfo=pytz.UTC)
        if dtend.tzinfo is None:
            dtend = dtend.replace(tzinfo=pytz.UTC)

        # Recurrence
        rrule_val = component.get("RRULE")
        if rrule_val:
            rrule_str_full = ";".join([f"{k}={v[0]}" for k,v in rrule_val.items() if str(v[0])])
            # Remove unsupported numeric-only properties
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
                        "start": occ_start,
                        "end": occ_end,
                        "all_day": all_day
                    })
            except Exception as e:
                print(f"Warning: skipping RRULE for '{summary}': {e}")
                events.append({
                    "summary": summary,
                    "start": dtstart,
                    "end": dtend,
                    "all_day": all_day
                })
        else:
            events.append({
                "summary": summary,
                "start": dtstart,
                "end": dtend,
                "all_day": all_day
            })

    return events

# -----------------------------
# Filter events for current week
# -----------------------------
def filter_week(events, reference_date=None):
    if reference_date is None:
        reference_date = datetime.datetime.now(pytz.timezone("Asia/Singapore"))
    elif reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=pytz.UTC)

    weekday = reference_date.weekday()  # Monday=0
    days_to_sunday = (weekday + 1) % 7
    start_of_week = (reference_date - datetime.timedelta(days=days_to_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + datetime.timedelta(days=6, hours=23, minutes=59, seconds=59)

    week_events = []
    for e in events:
        e_start, e_end = e['start'], e['end']
        if e_start.tzinfo is None:
            e_start = e_start.replace(tzinfo=pytz.UTC)
        if e_end.tzinfo is None:
            e_end = e_end.replace(tzinfo=pytz.UTC)
        # Overlaps with week?
        if e_end >= start_of_week and e_start <= end_of_week:
            e_copy = e.copy()
            if e_start < start_of_week:
                e_copy['start'] = start_of_week
            if e_end > end_of_week:
                e_copy['end'] = end_of_week
            week_events.append(e_copy)

    return week_events, start_of_week

# -----------------------------
# Generate HTML
# -----------------------------
def generate_html(events, start_of_week):
    days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

    # Determine earliest and latest hour
    all_day_height = 20
    hour_height = 60
    timed_events = [e for e in events if not e['all_day']]
    if timed_events:
        earliest = min(e['start'] for e in timed_events)
        latest = max(e['end'] for e in timed_events)
    else:
        earliest = start_of_week.replace(hour=8)
        latest = start_of_week.replace(hour=17)

    start_hour = earliest.hour
    end_hour = latest.hour + 1  # cut off after last event

    html = ['<!DOCTYPE html><html><head><meta charset="utf-8"><title>Kobo Calendar Timetable</title><style>']
    html.append('body {font-family:Monaco, monospace; background:#fff; margin:0; padding:0.5em;}')
    html.append('.container {display:flex; width:100%;}')
    html.append('.hour-labels {width:40px; display:flex; flex-direction:column; margin-top:40px;}')
    html.append('.hour-labels div {height:60px; font-size:0.7em; text-align:right; padding-right:2px; border-bottom:1px solid #eee;}')
    html.append('.week {display:flex; flex:1;}')
    html.append('.day-column {flex:1; position:relative; margin-left:2px;}')
    html.append('.day-column-header {text-align:center; font-weight:bold; font-size:0.9em; height:20px; line-height:20px; border-bottom:1px solid #ccc;}')
    html.append('.event {position:absolute; left:2px; right:2px; background:#555; color:#fff; font-size:0.75em; padding:1px; border-radius:2px; line-height:1em;}')
    html.append('.event .time {font-size:0.65em;}')
    html.append('.all-day {position:absolute; left:2px; right:2px; top:20px; background:#999; color:#fff; font-size:0.75em; padding:1px; border-radius:2px;}')
    html.append('</style></head><body>')
    html.append('<div class="container">')
    html.append('<div class="hour-labels">')
    for h in range(start_hour, end_hour):
        html.append(f'<div>{h:02d}:00</div>')
    html.append('</div>')
    html.append('<div class="week">')

    for i in range(7):
        day_date = start_of_week + datetime.timedelta(days=i)
        html.append(f'<div class="day-column"><div class="day-column-header">{days[i]} {day_date.day}</div>')
        # All-day events
        y_offset = all_day_height + 20
        day_events = [e for e in events if e['start'].date() == day_date.date() or (e['all_day'] and e['start'].date() <= day_date.date() <= e['end'].date())]
        # Place all-day events just under header
        ad_y = 20
        for e in day_events:
            if e['all_day']:
                html.append(f'<div class="all-day" style="top:{ad_y}px">{e["summary"]}</div>')
                ad_y += all_day_height
        # Timed events
        time_events = [e for e in day_events if not e['all_day']]
        for e in time_events:
            top = ((e['start'].hour + e['start'].minute/60) - start_hour) * hour_height + y_offset
            height = max(20, (e['end'] - e['start']).seconds / 3600 * hour_height)
            html.append(f'<div class="event" style="top:{top}px; height:{height}px;">'
                        f'{e["summary"]}<br>'
                        f'<span class="time">{e["start"].strftime("%H:%M")} - {e["end"].strftime("%H:%M")}</span>'
                        f'</div>')

        html.append('</div>')
    html.append('</div></div></body></html>')
    return "\n".join(html)

# -----------------------------
# Main
# -----------------------------
def main():
    import os
    urls = [os.environ.get("CALENDAR_ICS_URL"),
            os.environ.get("CALENDAR_ICS_URL_1"),
            os.environ.get("CALENDAR_ICS_URL_2")]
    all_events = []

    for u in urls:
        if u:
            try:
                cal = fetch_calendar(u)
                all_events.extend(parse_events(cal))
            except Exception as e:
                print(f"Error fetching/parsing {u}: {e}")

    now = datetime.datetime.now(pytz.timezone("Asia/Singapore"))
    week_events, start_of_week = filter_week(all_events, now)

    html = generate_html(week_events, start_of_week)
    try:
        with open("calendar.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("calendar.html written successfully")
    except Exception as e:
        print(f"Error writing calendar.html: {e}")

if __name__ == "__main__":
    main()
