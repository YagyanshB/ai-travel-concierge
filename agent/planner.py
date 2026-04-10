import datetime

def pick_dates():
    today = datetime.date.today()
    start = today + datetime.timedelta(days=60)
    end = start + datetime.timedelta(days=5)
    return start, end


def generate_basic_plan():
    return {
        "destination": "Barcelona",
        "flight_cost": 120,
        "stay_cost": 300
    }
