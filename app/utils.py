import random, string

def generate_unique_id():
    return "FG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
