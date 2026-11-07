import os
from dotenv import load_dotenv
from ollama import chat as ollama_chat

load_dotenv()
MODEL = os.environ["LLM_MODEL"]

def chat(messages, think=False, stream=False, schema=None, temperature=0.2):
    """Single entry point for every model call in Auction Room."""
    return ollama_chat(
        model=MODEL,
        messages=messages,
        think=think,
        stream=stream,
        format=schema,
        options={"temperature": temperature},
    )