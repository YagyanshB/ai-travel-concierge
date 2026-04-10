def can_afford_trip(finances):
    buffer = 2000  # safety savings
    return finances["savings"] - finances["travel_budget"] > buffer
