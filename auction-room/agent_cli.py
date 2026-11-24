"""Auction Room agent v0: the model decides when to look up stats.

Difference from chat_cli.py: there you picked the player and pasted their stats in
up front. Here the model gets a tool and fetches whatever it needs, for any player.
"""
import duckdb
import time
import re


from datetime import date
from auction_room import news

from auction_room.llm import chat
from auction_room.tools import REGISTRY, TOOLS

DB = "data/auction_room.duckdb"
MAX_STEPS = 5   # safety net: stop if the model keeps calling tools without answering

SYSTEM_PROMPT = f"""Today is {date.today():%d %B %Y}. The IPL 2027 auction is on 16 December 2026 in Goa;until then, nobody has been bought at it.
- You are an IPL analyst helping a franchise before the 2027 auction.
- For any question about a player's numbers, call get_player_stats. Never answer stats from memory.
- Answer only from what the tool returns, and quote the season and the number.
- When you pass on a tool's result, only quote numbers that appear in it.
- If the tool says several players match, ask the user which one they mean.
- If the data doesn't cover the question, say so plainly in one sentence.
- When you pass on a tool's result, only quote numbers that appear in it. Never add or calculate your own.
- Cite news only as [1], [2], matching the numbered excerpts from search_news for this question. Never write URLs or a Sources list; the app adds them.
- State something as fact only if the excerpts confirm it. If they only suggest or speculate, say it is not confirmed.
- the news search always returns something, so check whether the excerpts actually answer the question. If they don't, say the news you have doesn't cover it.
- Don't answer news questions from earlier results in the conversation; search again.
- Keep answers short."""
# Bring over your few-shot examples and the three refusal lines from chat_cli.py if you like.

def add_sources(answer: str) -> str:
    """The model cites by number; code owns the URLs."""
    answer = re.split(r"\n?\s*Sources:", answer)[0].rstrip()      # drop any Sources list the model wrote
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
    if not cited:
        return answer
    if not news.LAST_RESULTS:                                     # cited, but nothing was searched
        return re.sub(r"\s*\[\d+\]", "", answer) + "\n(Citations removed: no news was searched for this answer.)"
    lines = []
    for n in cited:
        if 1 <= n <= len(news.LAST_RESULTS):
            s = news.LAST_RESULTS[n - 1]
            lines.append(f"[{n}] {s['title']} ({s['site']}, {str(s['date'])[:10]}) {s['url']}")
        else:
            lines.append(f"[{n}] (not a real source: the model cited something it wasn't given)")
    return answer + "\n\nSources:\n" + "\n".join(lines)


def run_turn(con, messages) -> str:
    """One user question -> as many tool calls as needed -> the final answer."""
    for step in range(1, MAX_STEPS + 1):
        start = time.time()
        r = chat(messages, tools=TOOLS)

        print(f"[step {step} | model {time.time() - start:.1f}s | "
              f"{r.prompt_eval_count} in, {r.eval_count} out]")

        messages.append(r.message)   # the assistant's turn, tool calls included

        # TODO 3: if the model made no tool calls, this is its final answer: return the text.
        #         (look at r.message.tool_calls)
        if not r.message.tool_calls:
            return r.message.content


        # TODO 4: otherwise, for each call in r.message.tool_calls:
        #   a. name = call.function.name, args = call.function.arguments
        #      (in Ollama args is already a dict; in OpenAI's API it's a JSON string you'd json.loads)
        #   b. find the function in REGISTRY; if the name isn't there, the result is an error sentence
        #   c. result = fn(con, **args)
        #   d. print a log line so you can SEE the agent think, e.g.
        #        [tool] get_player_stats({'name': 'Kohli', 'season': 2016})
        #   e. messages.append({"role": "tool", "tool_name": name, "content": result})
        # Then the loop goes round: the model reads the results and either answers or calls again.
        for call in r.message.tool_calls:
            name = call.function.name
            args = call.function.arguments

            tool_start = time.time()

            findName = REGISTRY.get(name)
            if not findName:
                result = f"No tool identified by {name}"
            else:
                try:
                    result = findName(con, **args)
                except Exception as e:
                    result = f"Tool error in {name}: {e}"
            #print(f'{name} {args}')
            print(f"[tool] {name}({args}) | {time.time() - tool_start:.1f}s")

            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": result
            })


    return "Stopped: too many tool calls for one question."


def main():
    con = duckdb.connect(DB, read_only=True)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print("Auction Room agent. Ask about any IPL player (or 'quit').\n")

    while True:
        question = input("You › ").strip()
        if question.lower() in {"quit", "exit", ""}:
            break
        messages.append({"role": "user", "content": question})

        news.LAST_RESULTS.clear()
        answer = add_sources(run_turn(con, messages))     # the ONLY run_turn call

        # store the checked answer (run_turn may end on a tool message if it hit MAX_STEPS)
        last = messages[-1]
        if (last["role"] if isinstance(last, dict) else last.role) == "assistant":
            messages[-1] = {"role": "assistant", "content": answer}
        else:
            messages.append({"role": "assistant", "content": answer})
        print("AI  › " + answer + "\n")

        # keep the conversation, drop old tool traffic
        messages[:] = [m for m in messages
                       if (m["role"] if isinstance(m, dict) else m.role) in ("system", "user")
                       or ((m["role"] if isinstance(m, dict) else m.role) == "assistant"
                           and not (m.get("tool_calls") if isinstance(m, dict) else m.tool_calls))]


if __name__ == "__main__":
    main()