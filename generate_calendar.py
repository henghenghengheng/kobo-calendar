import os
import datetime
import requests
from icalendar import Calendar

# ------------------------------
# Configuration
# ------------------------------
CALENDAR_ICS_URL = os.environ.get("CALENDAR_ICS_URL")  # Your Google Calendar ICS URL
DAYS_AHEAD = 7
OUTPUT_HTML = "calendar.html"
HOUR_HEIGHT_PX = 60  # 1 hour = 60px
ALL_DAY_HEIGHT_PX = 20  # height of all-day event block
HEADER_HEIGHT_PX = 20   # height of header row

# ------------------------------
# Helper functions
# ------------------------------
def fetch_ics(url):
    response = requests.get(url)
    response.raise_for_status()
    return Calendar.from_ical(response.text)

def get_start_of_week(dt):
    """Return Sunday of the week containing dt"""
    return dt - datetime.timedelta(days=dt.weekday()+1 if dt.weekday() != 6 else 0)

def parse_events(cal):
    """Return list of dicts with keys: summary, start, end, all_day, location"""
    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
            start = component.get('dtstart').dt
            end = component.get('dtend').dt
            all_day = False
            if isinstance(start, datetime.date) and not isinstance(start, datetime.datetime):
                # all-day event
                start = datetime.datetime.combine(start, datetime.time())
                end = datetime.datetime.combine(end, datetime.time())
                all_day = True
            location = component.get('location')
            events.append({
                'summary': str(component.get('summary')),
                'start': start,
                'end': end,
                'all_day': all_day,
                'location': str(location) if location else ''
            })
    return events

def filter_week(events, reference_date=None):
    """Return events for this week (Sun-Sat)"""
    if reference_date is None:
        reference_date = datetime.datetime.now()
    start_of_week = get_start_of_week(reference_date)
    end_of_week = start_of_week + datetime.timedelta(days=7)
    week_events = []
    for e in events:
        if e['end'] > start_of_week and e['start'] < end_of_week:
            # truncate event to the week range
            e_copy = e.copy()
            if e_copy['start'] < start_of_week:
                e_copy['start'] = start_of_week
            if e_copy['end'] > end_of_week:
                e_copy['end'] = end_of_week
            week_events.append(e_copy)
    return week_events, start_of_week

def compute_earliest_latest(events):
    timed_events = [e for e in events if not e['all_day']]
    if not timed_events:
        return 8.0, 17.0  # fallback
    earliest = min(e['start'].hour + e['start'].minute/60 for e in timed_events)
    latest = max(e['end'].hour + e['end'].minute/60 for e in timed_events)
    return earliest, latest

def generate_html(events, start_of_week):
    # Separate all-day and timed events
    all_day_events = [e for e in events if e['all_day']]
    timed_events = [e for e in events if not e['all_day']]

    earliest_hour, latest_hour = compute_earliest_latest(events)
    hour_height = HOUR_HEIGHT_PX

    html = ['<!DOCTYPE html>',
            '<html><head><meta charset="utf-8"><title>Kobo Calendar</title>',
            '<style>',
            'body { font-family:sans-serif; background:#fff; color:#000; margin:0; padding:0.5em; }',
            '.container { display:flex; width:100%; }',
            '.hour-labels { width:40px; display:flex; flex-direction:column; margin-top:%dpx; }' % (ALL_DAY_HEIGHT_PX + HEADER_HEIGHT_PX),
            '.hour-labels div { height:%dpx; font-size:0.7em; text-align:right; padding-right:2px; border-bottom:1px solid #eee; }' % hour_height,
            '.week { display:flex; flex:1; }',
            '.day-column { flex:1; border-left:1px solid #ccc; position:relative; margin-left:2px; }',
            '.day-column-header { text-align:center; background:#eee; font-weight:bold; border-bottom:1px solid #ccc; height:%dpx; line-height:%dpx; }' % (HEADER_HEIGHT_PX, HEADER_HEIGHT_PX),
            '.event { position:absolute; left:2px; right:2px; background:#999; color:#fff; font-size:0.7em; padding:1px; border-radius:2px; line-height:1em; }',
            '.event .time { font-size:0.65em; }',
            '.event .location { font-size:0.65em; }',
            '.all-day { position:absolute; left:2px; right:2px; top:%dpx; background:#555; color:#fff; font-size:0.7em; padding:1px; border-radius:2px; }' % HEADER_HEIGHT_PX,
            '</style></head><body>']

    # Hour labels
    html.append('<div class="container">')
    html.append('<div class="hour-labels">')
    for h in range(int(earliest_hour), int(latest_hour)+1):
        html.append('<div>%02d:00</div>' % h)
    html.append('</div>')  # close hour-labels

    # Week columns
    html.append('<div class="week">')
    for i in range(7):
        day_date = start_of_week + datetime.timedelta(days=i)
        html.append('<div class="day-column">')
        html.append('<div class="day-column-header">%s %d</div>' % (day_date.strftime('%a'), day_date.day))

        # all-day events for this day
        y_offset = 0
        for e in all_day_events:
            if e['start'].date() <= day_date.date() <= (e['end'] - datetime.timedelta(seconds=1)).date():
                html.append('<div class="all-day" style="top:%dpx;">%s</div>' % (y_offset, e['summary']))
                y_offset += ALL_DAY_HEIGHT_PX

        # timed events
        for e in timed_events:
            if e['start'].date() <= day_date.date() <= e['end'].date():
                start_time = e['start']
                end_time = e['end']
                if start_time.date() < day_date.date():
                    start_time = datetime.datetime.combine(day_date.date(), datetime.time(int(earliest_hour)))
                if end_time.date() > day_date.date():
                    end_time = datetime.datetime.combine(day_date.date(), datetime.time(int(latest_hour)))
                top = (start_time.hour + start_time.minute/60 - earliest_hour) * hour_height + ALL_DAY_HEIGHT_PX + HEADER_HEIGHT_PX
                height = (end_time.hour + end_time.minute/60 - start_time.hour - start_time.minute/60) * hour_height
                html.append('<div class="event" style="top:%dpx; height:%dpx;">%s<br><span class="time">%s - %s</span>%s</div>' %
                            (top, height, e['summary'],
                             start_time.strftime('%H:%M'),
                             end_time.strftime('%H:%M'),
                             '<br><span class="location">%s</span>' % e['location'] if e['location'] else ''))

        html.append('</div>')  # close day-column
    html.append('</div>')  # close week
    html.append('</div>')  # close container
    html.append('</body></html>')

    return '\n'.join(html)

# ------------------------------
# Main
# ------------------------------
def main():
    if not CALENDAR_ICS_URL:
        raise ValueError("CALENDAR_ICS_URL environment variable not set")
    cal = fetch_ics(CALENDAR_ICS_URL)
    events = parse_events(cal)
    week_events, start_of_week = filter_week(events)
    html = generate_html(week_events, start_of_week)
    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Calendar HTML written to {OUTPUT_HTML}")

if __name__ == "__main__":
    main()
