import os, time
from dotenv import load_dotenv
from ollama import chat
from first_call import IPLFact, SYSTEM

load_dotenv()
start = time.time()
r = chat(
    model=os.environ["LLM_MODEL"],
    messages=[{"role": "system", "content": SYSTEM},
              {"role": "user", "content": "Give me one surprising fact about an IPL auction."}],
    think=False,
    format=IPLFact.model_json_schema(),   # forces the reply into your Pydantic schema
    options={"temperature": 0.2},
)
print(f"[{time.time() - start:.1f}s | {r.prompt_eval_count} in, {r.eval_count} out]")
print("thinking:", len(r.message.thinking or ""))
print(IPLFact.model_validate_json(r.message.content).model_dump_json(indent=2))