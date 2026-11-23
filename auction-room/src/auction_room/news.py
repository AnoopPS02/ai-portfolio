"""Search the news chunks by meaning, not by exact words."""
import ollama

EMBED_MODEL = "nomic-embed-text"
DIM = 768


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
            SELECT title, date, url, text,
                ROUND(array_cosine_similarity(embedding, ?::FLOAT[768])::DOUBLE,3) AS score
            FROM news_chunks
            QUALIFY ROW_NUMBER() OVER (PARTITION BY url ORDER BY score DESC) = 1
            ORDER BY score desc
            LIMIT ?
        """
    return con.execute(sql, [q_vec, k]).df()


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