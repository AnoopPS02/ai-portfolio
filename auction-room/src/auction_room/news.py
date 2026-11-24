"""Search the news chunks by meaning, not by exact words."""
import ollama

EMBED_MODEL = "nomic-embed-text"
DIM = 768

LAST_RESULTS: list[dict] = []

def search_news(con, query: str, k: int = 5):
    """Return the k chunks most similar in meaning to `query`, best first."""
    # Queries get a different prefix than documents. nomic-embed-text was trained this way:
    # a short question and the paragraph that answers it should land close together.
    q_vec = ollama.embed(model=EMBED_MODEL, input=["search_query: " + query]).embeddings[0]

    # TODO 2: one SQL query on news_chunks that returns title, date, url, text and a
    #   `score` column, ordered best first, top k only.
    #   - the similarity function is  array_cosine_similarity(embedding, ?::FLOAT[768])
    #     (1.0 = same meaning, around 0 = unrelated)
    #   - pass q_vec and k as ? parameters, never in the string
    #   - round the score to 3 decimals so it's readable
    sql = """
            SELECT title, date, url, site, text,
                ROUND(array_cosine_similarity(embedding, ?::FLOAT[768])::DOUBLE,3) AS score
            FROM news_chunks
            QUALIFY ROW_NUMBER() OVER (PARTITION BY url ORDER BY score DESC) = 1
            ORDER BY score desc
            LIMIT ?
        """
    return con.execute(sql, [q_vec, k]).df()

def format_results(df) -> str:
    """Numbered sources the model can cite as [1], [2]..."""
    blocks = []
    for i, r in enumerate(df.itertuples(), start=1):
        # TODO A: one block per result, e.g.
        #   [1] <title> (<site>, <date as YYYY-MM-DD>) <url>
        #   <the chunk text, without the title line at the start>
        #   Hint: the chunk text begins with the title + "\n" (that's how you built it),
        #   so r.text[len(r.title) + 1:] is the body. str(r.date)[:10] gives YYYY-MM-DD.      
        blocks.append(f"[{i}] {r.title} ({r.site}, {str(r.date)[:10]}) {r.url}\n{r.text[len(r.title) + 1:]}")

    return "\n\n".join(blocks) if blocks else "No news found."

def search_news_tool(con, query: str) -> str:
    df = search_news(con, query, k=4)
    LAST_RESULTS[:] = df[["title", "site", "date", "url"]].to_dict("records")
    return format_results(df)


SEARCH_NEWS = {
    "type": "function",
    "function": {
        "name": "search_news",
        # TODO B: the 3-part description.
        #   Returns: news excerpts about IPL 2027 retentions, releases, trades, captaincy and
        #            the auction (Oct 26 - Nov 19, 2026), numbered for citing
        #   Use it for: why/what-happened/latest-news questions; anything the stats tools can't know
        #   Doesn't have: news after Nov 19, live auction results, player stats (use the other tools)
        "description": (
            "Returns: news excerpts about IPL 2027 retentions, releases, trades, captaincy and the auction (Oct 26 - Nov 19, 2026), numbered for citing. "
            "Use it for: why/what-happened/latest-news questions; anything the stats tools can't know. "
            "Doesn't have: news after Nov 19, live auction results, player stats (use the other tools). "
        ),
        "parameters": {
            "type": "object",
            "properties": {
                # TODO C: one property, `query`: what to search for, in plain words
                "query":{
                    "type": "string",
                    "description": (
                        "what to search for, in plain words e.g. 'why was Mitchell Starc released'"
                        "Which players retained by Chennai super kings"
                    ),
                }
            },
            "required": ["query"],   # TODO C
        },
    },
}


if __name__ == "__main__":
    # Try it:  uv run python -m auction_room.news
    import duckdb
    con = duckdb.connect("data/auction_room.duckdb", read_only=True)
    for q in ["Why was Mitchell Starc released?",
              "Which team traded for Hardik Pandya and for how much?",
              "When and where is the IPL 2027 auction?",
              "Who will captain KKR next season?"]:
        print(f"\n=== {q}")
        for r in search_news(con, q, k=3).itertuples():
            print(f"[{r.score}] {r.date} {r.title[:60]}\n    {r.text[len(r.title)+1:][:160]!r}")