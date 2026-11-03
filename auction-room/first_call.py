import os, time
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ValidationError

load_dotenv()
client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])
MODEL = os.environ["LLM_MODEL"]

class IPLFact(BaseModel):
    fact: str
    season: int
    category: str    # batting, bowling, auction or team
    confidence: str  # high, medium or low

SYSTEM = """You are a cricket statistician for the IPL.
Reply with ONLY a JSON object with keys: fact (string), season (integer year),
category (one of: batting, bowling, auction, team), confidence (high, medium or low).
If you are not sure a fact is true, set confidence to low. /no_think"""

def ask(question: str, temperature: float = 1.0) -> IPLFact:
    start = time.time()
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=temperature,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": question}],
        extra_body={"think": False},
    )
    msg = resp.choices[0].message
    extra = msg.model_dump()
    print("message fields:", list(extra.keys()))
    print("reasoning length:", len(str(extra.get("reasoning") or extra.get("reasoning_content") or "")))
    text = resp.choices[0].message.content.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if resp.usage:
        print(f"[{time.time() - start:.1f}s | {resp.usage.prompt_tokens} tokens in, "
              f"{resp.usage.completion_tokens} out]")
    return IPLFact.model_validate_json(text)

if __name__ == "__main__":
    for q in ["Give me one surprising fact about an IPL auction.",
              "Who was the most expensive buy at the most recent IPL auction?"]:
        try:
            print(ask(q).model_dump_json(indent=2))
        except ValidationError as e:
            print("Not valid JSON for our schema:", e)