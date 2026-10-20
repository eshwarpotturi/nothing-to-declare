"""Dates for the disclosure window: the manuscript "received" date and the Open Payments years to check.

The ICMJE form asks about relationships in the 36 months before submission. Papers are often received
months before they are published, so the window is anchored on the received date when the paper gives one.
"""
import re
from datetime import date, timedelta

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
# Text form some full-text XML uses instead of a <date>: "Received 2023 Sep 5; Accepted 2024 May 17; ..."
RECEIVED_TEXT = re.compile(r"\bReceived:?\s+(\d{4})\s+([A-Za-z]{3})[a-z]*\.?(?:\s+(\d{1,2}))?")


def _int(el):
    try:
        return int("".join(el.itertext()).strip()) if el is not None else None
    except ValueError:
        return None


def received_date(root):
    """ISO date (YYYY-MM-DD) from <history><date date-type="received"> in JATS XML, or None.

    Also reads the newer form <pub-history><event event-type="received"><date>, and the plain-text note
    <sec sec-type="history"><p>Received 2023 Sep 5; ...</p></sec>.
    Needs at least a year and a month; a missing day is taken as the 1st."""
    dates = [d for d in root.iter("date") if d.get("date-type") == "received"]
    dates += [d for ev in root.iter("event") if ev.get("event-type") == "received" for d in ev.iter("date")]
    for d in dates:
        iso = (d.get("iso-8601-date") or "")[:10]
        try:
            return date.fromisoformat(iso).isoformat()
        except ValueError:
            pass
        y, m, dd = _int(d.find("year")), _int(d.find("month")), _int(d.find("day"))
        if not y or not m:
            return None
        try:
            return date(y, m, dd or 1).isoformat()
        except ValueError:
            try:
                return date(y, m, 1).isoformat()  # bad day (e.g. 31 June): keep the month
            except ValueError:
                return None
    for sec in root.iter("sec"):
        if sec.get("sec-type") != "history":
            continue
        m = RECEIVED_TEXT.search(" ".join(sec.itertext()))
        if m and m.group(2).lower() in MONTHS:
            y, mo, dd = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3) or 1)
            try:
                return date(y, mo, dd).isoformat()
            except ValueError:
                return date(y, mo, 1).isoformat()
    return None


def anchor(paper, mode="received"):
    """(anchor date, basis) for a step-1 paper record. Falls back to the publication date when the received
    date is missing, later than publication, or mode is 'published'. Old step-1 records have no 'received' key."""
    pub = date.fromisoformat(paper["date"][:10])
    rec = paper.get("received")
    if mode == "received" and rec:
        try:
            r = date.fromisoformat(rec[:10])
            if r <= pub:
                return r, "received"
        except ValueError:
            pass
    return pub, "published"


def months_before(d, months):
    """The date `months` calendar months before d (day clipped to the month's length)."""
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue


def program_years(anchor_date, months=36, rule="inside"):
    """Open Payments program years (calendar years) to check for a paper.

    The window is the `months` before anchor_date. The pipeline pulls yearly totals per company and payment
    type, not individual payment dates, so a part-year cannot be split. Two rules:
      inside  (default): only years that sit wholly inside the window. Every payment counted is certainly
                         within the 36 months, so every flag is safe to defend. Some real payments in the
                         part-years at either end are missed.
      overlap: every year that touches the window counts in full. Catches more, but can count payments
               outside the 36 months.
    Example: received 2024-03-15 -> window 2021-03-15 to 2024-03-14 -> inside: 2022, 2023;
    overlap: 2021, 2022, 2023, 2024."""
    start = months_before(anchor_date, months)
    end = anchor_date - timedelta(days=1)  # the window ends the day before the anchor date
    if rule == "overlap":
        return set(range(start.year, end.year + 1))
    if rule != "inside":
        raise ValueError(f"unknown year rule: {rule}")
    return {y for y in range(start.year, end.year + 1) if date(y, 1, 1) >= start and date(y, 12, 31) <= end}
