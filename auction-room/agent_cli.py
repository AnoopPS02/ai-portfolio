"""Auction Room agent v0: the model decides when to look up stats.

Difference from chat_cli.py: there you picked the player and pasted their stats in
up front. Here the model gets a tool and fetches whatever it needs, for any player.
"""
import duckdb

from auction_room.llm import chat
from auction_room.tools import REGISTRY, TOOLS

DB = "data/auction_room.duckdb"
MAX_STEPS = 5   # safety net: stop if the model keeps calling tools without answering

SYSTEM_PROMPT = """You are an IPL analyst helping a franchise before the 2027 auction.
- For any question about a player's numbers, call get_player_stats. Never answer stats from memory.
- Answer only from what the tool returns, and quote the season and the number.
- If the tool says several players match, ask the user which one they mean.
- If the data doesn't cover the question, say so plainly in one sentence.
- Keep answers short."""
# Bring over your few-shot examples and the three refusal lines from chat_cli.py if you like.


def run_turn(con, messages) -> str:
    """One user question -> as many tool calls as needed -> the final answer."""
    for _ in range(MAX_STEPS):
        r = chat(messages, tools=TOOLS)
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

            findName = REGISTRY.get(name)
            if not findName:
                result = f"No tool identified by {name}"
            else:
                result = findName(con, **args)
            print(f'{name} {args}')

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
        print("AI  › " + run_turn(con, messages) + "\n")


if __name__ == "__main__":
    main()