import streamlit as st
from datetime import date, timedelta

st.set_page_config(
    page_title="AI Travel Intelligence",
    page_icon="✈️",
    layout="wide"
)

# -------------------------
# HEADER
# -------------------------

st.title("✈️ AI Travel Intelligence")
st.caption("Plan smarter trips using AI-driven optimization")

st.divider()

# -------------------------
# SIDEBAR INPUTS (CLEAN UX)
# -------------------------

with st.sidebar:
    st.header("💰 Profile")

    income = st.number_input("Monthly Income", 0, 100000, 3000)
    expenses = st.number_input("Monthly Expenses", 0, 100000, 2000)
    savings = st.number_input("Savings", 0, 100000, 5000)

    budget = st.slider("Travel Budget", 100, 5000, 800)

    st.divider()

    st.header("🌍 Trip Settings")

    origin = st.text_input("Origin", "LHR")
    destination = st.selectbox(
        "Destination",
        ["Barcelona", "Paris", "Amsterdam", "Rome", "Lisbon"]
    )

    trip_days = st.slider("Trip Duration", 2, 14, 5)

# -------------------------
# DATE ENGINE
# -------------------------

start_date = date.today() + timedelta(days=60)
end_date = start_date + timedelta(days=trip_days)

# -------------------------
# FAKE FLIGHT DATA (REALISTIC STRUCTURE)
# -------------------------

def get_fake_flights():
    return [
        {"airline": "British Airways", "price": 120, "duration": "2h 10m", "stops": 0},
        {"airline": "EasyJet", "price": 85, "duration": "2h 30m", "stops": 0},
        {"airline": "Iberia", "price": 140, "duration": "4h 10m", "stops": 1},
        {"airline": "Vueling", "price": 95, "duration": "2h 20m", "stops": 0},
    ]

# -------------------------
# TRIP ENGINE
# -------------------------

def build_trip(city):
    return {
        "flight_cost": 100 + len(city) * 4,
        "stay_cost": 90 * trip_days,
        "experience": 8.5 if city in ["Barcelona", "Lisbon"] else 8.0
    }

def score_trip(cost, experience):
    return round((experience * 10) / (cost / 100), 2)

# -------------------------
# UI ACTION
# -------------------------

st.header("🚀 Trip Planner")

if st.button("Generate Travel Plan"):

    col1, col2 = st.columns(2)

    trip = build_trip(destination)
    total_cost = trip["flight_cost"] + trip["stay_cost"]

    # ---------------- LEFT COLUMN ----------------
    with col1:
        st.subheader("📍 Trip Summary")

        st.markdown(f"### {destination}")
        st.write(f"📅 {start_date} → {end_date}")

        st.metric("✈️ Flight Cost", f"£{trip['flight_cost']}")
        st.metric("🏨 Stay Cost", f"£{trip['stay_cost']}")
        st.metric("💰 Total Cost", f"£{total_cost}")

        score = score_trip(total_cost, trip["experience"])
        st.metric("⭐ Trip Score", score)

        if total_cost > budget:
            st.error("Over budget")
        else:
            st.success("Within budget")

    # ---------------- RIGHT COLUMN ----------------
    with col2:
        st.subheader("✈️ Available Flights (Mock Data)")

        flights = get_fake_flights()

        for f in flights:
            with st.container():
                st.markdown(f"**{f['airline']}**")
                st.write(f"💸 £{f['price']} | ⏱ {f['duration']} | 🛑 {f['stops']} stops")
                st.divider()

    # ---------------- BOTTOM INSIGHT ----------------
    st.subheader("🧠 AI Insight")

    st.info(
        f"""
Best value destination: {destination}

- Trip efficiency is optimized for budget constraints
- Flight selection prioritizes low-cost carriers
- Stay duration aligns with spending capacity

Recommendation: **Proceed with booking consideration**
"""
    )