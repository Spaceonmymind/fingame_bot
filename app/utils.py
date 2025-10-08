import random, string

def generate_unique_id():
    return "FG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

slots = {
    "08.10.2025": ["11:20-12:00", "15:50-16:30"],
    "09.10.2025": ["11:20-12:00", "15:50-16:30"],
    "10.10.2025": ["11:50-12:30", "13:50-14:30"]
}
