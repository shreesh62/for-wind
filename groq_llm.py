import re
from groq import Groq
# Comment out or remove this line since it's causing error
# from memory_core import should_continue

client = Groq(api_key="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")

def remove_think_blocks(text):
    # Remove all <think>...</think> blocks and their contents completely
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return cleaned.strip()

def query_qwen(prompt, memory_snippet=""):
    final_prompt = (memory_snippet + " " + prompt).strip()

    # Temporarily skip this check
    # if not should_continue(final_prompt):
    #     return "Sorry, your request is too long for me to handle."

    try:
        response = client.chat.completions.create(
            model="qwen-qwq-32b",
            messages=[
                {"role": "system", "content": "You are Jarvis, a helpful AI assistant."},
                {"role": "user", "content": final_prompt}
            ],
            temperature=0.7,
            max_tokens=1024
        )

        raw_result = response.choices[0].message.content.strip()
        final_result = remove_think_blocks(raw_result)

        if not final_result:
            return raw_result
        return final_result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Groq API error: {str(e)}"
