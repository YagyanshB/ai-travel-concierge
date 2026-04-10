import os
from dotenv import load_dotenv

load_dotenv()  # must run before getenv

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))



client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_trip_summary(plan, dates, budget):
    prompt = f"""
    Create a short travel summary.

    Destination: {plan['destination']}
    Dates: {dates[0]} to {dates[1]}
    Budget: {budget}
    Cost: {plan['flight_cost'] + plan['stay_cost']}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content
