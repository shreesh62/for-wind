"""Simple PydanticAI verification script."""

import os
from dotenv import load_dotenv
from pydantic_ai import Agent

load_dotenv()

# Use Groq since you already have a GROQ_API_KEY configured
agent = Agent('groq:llama-3.3-70b-versatile')

result = agent.run_sync('Say hello in exactly 5 words.')
print(f"Agent response: {result.output}")
