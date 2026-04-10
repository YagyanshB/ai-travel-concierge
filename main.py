import json
from agent.budget import can_afford_trip
from agent.planner import pick_dates, generate_basic_plan
from agent.llm import generate_trip_summary
from agent.notifier import print_plan

def load_finances():
    with open("data/finances.json") as f:
        return json.load(f)

def load_template():
    with open("templates/leave_request.txt") as f:
        return f.read()

def main():
    finances = load_finances()

    if not can_afford_trip(finances):
        print("❌ Not enough savings for a trip.")
        return

    dates = pick_dates()
    plan = generate_basic_plan()

    total_cost = plan["flight_cost"] + plan["stay_cost"]

    if total_cost > finances["travel_budget"]:
        print("❌ Trip exceeds budget.")
        return

    summary = generate_trip_summary(plan, dates, finances["travel_budget"])

    template = load_template()
    leave_request = template.format(
        start_date=dates[0],
        end_date=dates[1]
    )

    print_plan(summary, leave_request)

    approve = input("\nApprove this trip? (yes/no): ")

    if approve.lower() == "yes":
        print("\n✅ Trip approved! (Manual booking for now)")
    else:
        print("\n❌ Trip cancelled.")

if __name__ == "__main__":
    main()
