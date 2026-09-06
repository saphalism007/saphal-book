"""
Asking for money that is late.

The ageing report has said for a long time who owes what and for how long, and
then stopped. Knowing is not collecting. What was missing was the short step
between the two: a list of who to chase today, worst first, with the reminder
already written.

Nothing is sent from here. This software has no business opening somebody's
mail account or messaging their customers on their behalf, and a reminder that
went out without being read first is a reminder that will one day go to the
wrong person or say the wrong figure. What it does is write the thing, in
English and in Nepali, ready to be read and sent.

Overdue means past the credit days agreed with that customer, not merely
unpaid. A bill inside its terms is ordinary trade and putting it on a chasing
list would train everybody to ignore the list.
"""

from ..core import money, nepali_date as nd
from . import reports

SIDES = {
    "receivable": {"who": "customer", "verb": "owes you"},
    "payable": {"who": "supplier", "verb": "you owe"},
}


def overdue(conn, side="receivable", as_at_ad=None, grace_days=0):
    """
    Who is late, worst first.

    Sorted by how old the oldest bill is rather than by how much is owed,
    because a small debt going back a year is a different problem from a large
    one that went past its date last week, and the first is the one that turns
    into a bad debt.
    """
    if side not in SIDES:
        raise ValueError("receivable or payable")
    as_at_ad = as_at_ad or nd.bs_to_ad(*nd.today_bs()).isoformat()
    ageing = reports.ageing(conn, side, as_at_ad)

    people = []
    for row in ageing.get("rows", []):
        credit = (row.get("credit_days") or 0) + grace_days
        late = []
        for bill in row.get("details", []):
            if bill.get("amount", 0) <= 0:
                continue
            age = bill.get("age_days") or 0
            if age <= credit:
                continue
            late.append({
                "number": bill.get("number"), "voucher_id": bill.get("voucher_id"),
                "date_bs": bill.get("date_bs"), "date_ad": bill.get("date_ad"),
                "amount": bill["amount"], "age_days": age,
                "days_over": age - credit,
            })
        if not late:
            continue
        late.sort(key=lambda bill: -bill["age_days"])
        people.append({
            "party_id": row.get("party_id"), "account_id": row.get("account_id"),
            "name": row.get("name"), "pan": row.get("pan") or "",
            "phone": row.get("phone") or "",
            "credit_days": row.get("credit_days") or 0,
            "bills": late,
            "amount": sum(bill["amount"] for bill in late),
            "count": len(late),
            "oldest_days": late[0]["age_days"],
            "total_owed": row.get("total", 0),
        })

    people.sort(key=lambda person: (-person["oldest_days"], -person["amount"]))
    return {
        "side": side, "as_at_ad": as_at_ad, "rows": people,
        "total": sum(person["amount"] for person in people),
        "count": len(people),
        "bills": sum(person["count"] for person in people),
    }


def reminder(conn, person, language="en"):
    """
    The message itself, ready to be read and then sent.

    Every bill is named with its date and amount, because a reminder that only
    gives a total invites an argument about which bills it covers, and that
    argument costs more than the letter.
    """
    company = conn.execute("SELECT name, phone, mobile FROM company WHERE id = 1").fetchone()
    house = company["name"] if company else ""
    reach = (company["mobile"] or company["phone"]) if company else ""

    if language == "np":
        lines = ["आदरणीय %s," % person["name"], ""]
        lines.append("तपाईंको नाममा रु. %s बक्यौता रहेको जानकारी गराउँदछौं। "
                     "विवरण यसप्रकार छ:" % money.format_money(person["amount"]))
        lines.append("")
        for bill in person["bills"]:
            lines.append("  %s, मिति %s, रु. %s, %d दिन नाघेको"
                         % (bill["number"], bill["date_bs"],
                            money.format_money(bill["amount"]), bill["days_over"]))
        lines.append("")
        lines.append("कृपया यथाशीघ्र भुक्तानीको व्यवस्था गरिदिनुहुन अनुरोध छ। "
                     "भुक्तानी भइसकेको भए यो सन्देशलाई बेवास्ता गर्नुहोला।")
        lines.append("")
        lines.append("धन्यवाद।")
        lines.append(house)
        if reach:
            lines.append(reach)
        return "\n".join(lines)

    lines = ["Dear %s," % person["name"], ""]
    lines.append("Our records show %s outstanding on the following bills:"
                 % money.format_money(person["amount"]))
    lines.append("")
    for bill in person["bills"]:
        lines.append("  %s dated %s   %s   %d days past due"
                     % (bill["number"], bill["date_bs"],
                        money.format_money(bill["amount"]), bill["days_over"]))
    lines.append("")
    lines.append("We would be grateful if you could arrange payment. If it has "
                 "already been sent, please treat this as settled and accept our "
                 "thanks.")
    lines.append("")
    lines.append("Regards,")
    lines.append(house)
    if reach:
        lines.append(reach)
    return "\n".join(lines)


def with_reminders(conn, side="receivable", as_at_ad=None, grace_days=0):
    """The list, with each message already written."""
    found = overdue(conn, side, as_at_ad, grace_days)
    for person in found["rows"]:
        person["message_en"] = reminder(conn, person, "en")
        person["message_np"] = reminder(conn, person, "np")
    return found
