from datetime import datetime
from math import ceil

# dt = datetime.today().strftime("%Y_%m")

dt = datetime.today()


def get_week_of_month(dt):
    first_day = datetime.today().replace(day=1)
    day_of_month = dt.day
    if first_day.weekday() == 6:
        adjusted_dom = (1 + first_day.weekday()) / 7
    else:
        adjusted_dom = day_of_month + first_day.weekday()
    return int(ceil(adjusted_dom / 7.0))


dt = datetime.today()
week_of_month = get_week_of_month(dt)
a = dt.strftime("%Y_%m")
print(f"{a}_week_{week_of_month}")
