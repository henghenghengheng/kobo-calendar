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
    print(f"Fetching calendar: {url}")
    try:
        r = requests.get(url)
        r.raise_for_status()
        return Calendar.from_ical(r.text)
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

# -----------------------------
# Parse events
# -----------------------------
def parse_events(cal, start_range=None, end_range=None):
    events = []
    if not cal:
        return events

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("SUMMARY"))
        location = str(component.get("LOCATION", ""))
        dtstart_prop = component.get("DTSTART")
        dtend_prop = component.get("DTEND")

        if not dtstart_prop:
            continue  # skip events without DTSTART

        dtstart = dtstart_prop.dt

        # Handle missing DTEND
        if dtend_prop is not None:
            dtend = dtend_prop.dt
        else:
            if isinstance(dtstart, datetime.date) and not isinstance(dtstart, datetime.datetime):
                dtend = dtstart + datetime.timedelta(days=1)
            else:
                dtend = dtstart + datetime.timedelta(hours=1)

        all_day = False
        # All-day events
        if isinstance(dtstart, datetime.date) and not isinstance(dtstart, datetime.datetime):
            all_day = True
            dtstart = datetime.datetime.combine(dtstart, datetime.time.min)
            dtend = datetime.datetime.combine(dtend, datetime.time.min)
        # Timezone
        if dtstart.tzinfo is None:
            dtstart = dtstart.replace(tzinfo=pytz.UTC)
        if dtend.tzinfo is None:
            dtend = dtend.replace(tzinfo=pytz.UTC)

        # Handle recurrence
        rrule_val = component.get("RRULE")
        occurrences = []
        if rrule_val:
            rrule_str_full = ";".join([f"{k}={v[0]}" for k, v in rrule_val.items() if str(v[0])])
            rrule_str_clean = re.sub(r'(?:^|;)\d+=\d+', '', rrule_str_full)
            try:
                rrule_obj = rrulestr(rrule_str_clean, dtstart=dtstart)
                if start_range and end_range:
                    occurrences = list(rrule_obj.between(start_range, end_range, inc=True))
                else:
                    occurrences = list(rrule_obj)
            except Exception as e:
                print(f"Skipping unsupported RRULE for '{summary}': {e}")
                occurrences = [dtstart]
        else:
            occurrences = [dtstart]

        # Handle EXDATEs
        exdates = []
        exdate_prop = component.get("EXDATE")
        if exdate_prop:
            if not isinstance(exdate_prop, list):
                exdate_prop = [exdate_prop]
            for ex in exdate_prop:
                for ex_dt in ex.dts:
                    ex_dtval = ex_dt.dt
                    if ex_dtval.tzinfo is None:
                        ex_dtval = ex_dtval.replace(tzinfo=pytz.UTC)
                    exdates.append(ex_dtval)

        for occ_start in occurrences:
            if occ_start in exdates:
                continue
            occ_end = occ_start + (dtend - dtstart)
            events.append({
                "summary": summary,
                "location": location,
                "start": occ_start,
                "end": occ_end,
                "all_day": all_day
            })
    return events

# -----------------------------
# Filter events for the current week
# -----------------------------
def filter_week(events, reference_date=None):
    if reference_date is None:
        reference_date = datetime.datetime.now(pytz.timezone("Asia/Singapore"))
    elif reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=pytz.UTC)

    weekday = reference_date.weekday()  # Mon=0
    days_to_sunday = (weekday + 1) % 7
    start_of_week = (reference_date - datetime.timedelta(days=days_to_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + datetime.timedelta(days=6, hours=23, minutes=59, seconds=59)

    week_events = []
    for e in events:
        s, e_end = e['start'], e['end']
        if s.tzinfo is None:
            s = s.replace(tzinfo=pytz.UTC)
        if e_end.tzinfo is None:
            e_end = e_end.replace(tzinfo=pytz.UTC)
        # overlaps week
        if e_end >= start_of_week and s <= end_of_week:
            copy = e.copy()
            if s < start_of_week:
                copy['start'] = start_of_week
            if e_end > end_of_week:
                copy['end'] = end_of_week
            week_events.append(copy)
    return week_events, start_of_week

# -----------------------------
# Generate HTML
# -----------------------------
def generate_html(events, start_of_week):
    days = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
    # Determine timeline bounds
    min_hour = 23
    max_hour = 0
    for e in events:
        if not e['all_day']:
            h1 = e['start'].hour
            h2 = e['end'].hour + (1 if e['end'].minute>0 else 0)
            min_hour = min(min_hour,h1)
            max_hour = max(max_hour,h2)
    if min_hour >= max_hour:
        min_hour = 8
        max_hour = 18

    html = ['<!DOCTYPE html><html><head><meta charset="utf-8"><title>Kobo Calendar</title><style>']
    html.append('body{font-family:Monaco, monospace; margin:0.5em;}')
    html.append('.container{display:flex; width:100%;}')
    html.append('.hour-labels{width:40px; display:flex; flex-direction:column; margin-top:40px;}')
    html.append('.hour-labels div{height:60px; font-size:0.7em; text-align:right; padding-right:2px;}')
    html.append('.week{display:flex; flex:1;}')
    html.append('.day-column{flex:1; position:relative; margin-left:2px;}')
    html.append('.day-column-header{text-align:center; font-weight:bold; height:20px; line-height:20px; font-size:0.85em;}')
    html.append('.event{position:absolute; left:2px; right:2px; background:#333; color:#fff; font-size:0.75em; padding:1px; border-radius:2px; line-height:1em;}')
    html.append('.all-day{position:absolute; left:2px; right:2px; top:20px; background:#555; color:#fff; font-size:0.75em; padding:1px; border-radius:2px;}')
    html.append('</style></head><body>')
    # simple password protection
    html.append('''<script>
if (!localStorage.getItem("kobo_pw")) {
    var pw = prompt("Enter password:");
    if(pw==="2603"){localStorage.setItem("kobo_pw","1");} else{document.body.innerHTML="<h1>Wrong password</h1>";}
}
</script>''')

    html.append('<div class="container">')
    html.append('<div class="hour-labels">')
    for h in range(min_hour, max_hour+1):
        html.append(f'<div>{h:02d}:00</div>')
    html.append('</div>')
    html.append('<div class="week">')

    for i in range(7):
        day_date = start_of_week + datetime.timedelta(days=i)
        html.append(f'<div class="day-column"><div class="day-column-header">{days[i]} {day_date.day}</div>')
        y_offset = 20 + 20  # header + all-day space

        # All-day events
        all_day_events = [e for e in events if e['all_day'] and e['start'].date() <= day_date.date() <= e['end'].date()]
        ad_top = 20
        for e in all_day_events:
            html.append(f'<div class="all-day" style="top:{ad_top}px;">{e["summary"]}</div>')
            ad_top += 18

        # Timed events
        timed_events = [e for e in events if not e['all_day'] and e['start'].date()==day_date.date()]
        # handle concurrent events: simple side-by-side
        timed_events.sort(key=lambda x:x['start'])
        slots = []
        for e in timed_events:
            top = y_offset + (e['start'].hour - min_hour)*60 + e['start'].minute
            height = max(20, (e['end']-e['start']).seconds/60)
            # find slot index
            idx = 0
            while any((top < s['top']+s['height'] and top+s['height']>s['top']) for s in slots if s['idx']==idx):
                idx += 1
            slots.append({'top':top,'height':height,'idx':idx})
            left_pct = idx * (100/len(slots))
            width_pct = 100 / (idx+1)
            html.append(f'<div class="event" style="top:{top}px; height:{height}px; left:{left_pct}%; width:{width_pct}%;">'
                        f'{e["summary"]}<br><span class="time">{e["start"].strftime("%H:%M")} - {e["end"].strftime("%H:%M")}</span><br>'
                        f'<span class="location">{e["location"]}</span></div>')

        html.append('</div>')  # day-column
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
            cal = fetch_calendar(u)
            all_events.extend(parse_events(cal))

    now = datetime.datetime.now(pytz.timezone("Asia/Singapore"))
    week_events, start_of_week = filter_week(all_events, now)
    html = generate_html(week_events, start_of_week)

    # write
    with open("calendar.html","w",encoding="utf-8") as f:
        f.write(html)
    print("calendar.html updated successfully.")

if __name__=="__main__":
    main()
