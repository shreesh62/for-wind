# --- Constants ---
INPUT_COST = 0.29 / 1_000_000   # $0.29 per 1M input tokens
OUTPUT_COST = 0.39 / 1_000_000  # $0.39 per 1M output tokens
SPENDING_LIMIT = 2.00           # Total dollars you're okay spending

# --- Variables ---
total_spent = 0.0

def estimate_cost(input_tokens, output_tokens):
    input_cost = input_tokens * INPUT_COST
    output_cost = output_tokens * OUTPUT_COST
    return input_cost + output_cost

def should_continue(input_tokens, output_tokens):
    global total_spent
    cost = estimate_cost(input_tokens, output_tokens)
    if total_spent + cost > SPENDING_LIMIT:
        print(f"🛑 Limit exceeded. Estimated total = ${total_spent + cost:.2f}")
        return False
    total_spent += cost
    return True
