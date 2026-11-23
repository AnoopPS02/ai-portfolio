"""Chunk the saved articles, embed each chunk locally, and store them in DuckDB.

Table created (rebuilt on every run):
  news_chunks  chunk_id, url, title, date, site, chunk_no, text, embedding FLOAT[768]

Setup: ollama pull nomic-embed-text      (small embedding model, ~270 MB)
Run:   uv run python build_news_index.py
"""
import json
from pathlib import Path

import duckdb
import ollama
import pandas as pd

ARTICLES = Path("data/raw/news/articles")
DB = "data/auction_room.duckdb"
EMBED_MODEL = "nomic-embed-text"
DIM = 768                     # nomic-embed-text returns 768 numbers per text
MAX_CHARS = 1000              # target chunk size
BATCH = 32                    # chunks per embedding call


def chunk(text: str) -> list[str]:
    """Split an article into chunks of about MAX_CHARS, without cutting paragraphs.

    trafilatura separates paragraphs with "\\n".
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    # TODO 1: pack whole paragraphs into chunks.
    #   - keep a `current` list of paragraphs and add the next one while the total
    #     length stays <= MAX_CHARS
    #   - when the next paragraph won't fit, save "\n".join(current) to chunks and start
    #     a new `current` that BEGINS with the last paragraph of the previous chunk
    #     (that one-paragraph overlap keeps context across the cut)
    #   - after the loop, save whatever is left in `current`
    #   - a single paragraph longer than MAX_CHARS just becomes its own chunk

    current = []
    for paragraph in paragraphs:
        if current and len("\n".join(current + [paragraph])) > MAX_CHARS:
            chunks.append("\n".join(current))
            current = [current[-1]]

        current.append(paragraph)

    if current:
        chunks.append("\n".join(current))
        
    return chunks


def embed(texts: list[str]) -> list[list[float]]:
    """Text -> vectors. nomic-embed-text wants a task prefix: documents get 'search_document: '."""
    vectors = []
    for i in range(0, len(texts), BATCH):
        batch = ["search_document: " + t for t in texts[i:i + BATCH]]
        vectors.extend(ollama.embed(model=EMBED_MODEL, input=batch).embeddings)
        print(f"  embedded {min(i + BATCH, len(texts))}/{len(texts)}")
    return vectors


def main():
    rows = []
    for path in sorted(ARTICLES.glob("*.json")):
        a = json.loads(path.read_text(encoding="utf-8"))
        for n, text in enumerate(chunk(a["text"])):
            rows.append({"chunk_id": f"{path.stem}-{n}", "url": a["url"], "title": a["title"],
                         "date": a["date"], "site": a["site"], "chunk_no": n,
                         # the title goes into every chunk so a chunk still says what it's about
                         "text": f"{a['title']}\n{text}"})
    print(f"{len(rows)} chunks from {len(list(ARTICLES.glob('*.json')))} articles")

    chunks_df = pd.DataFrame(rows)
    chunks_df["embedding"] = embed(chunks_df["text"].tolist())

    con = duckdb.connect(DB)
    con.execute(f"""
        CREATE OR REPLACE TABLE news_chunks AS
        SELECT * EXCLUDE (embedding, date),
               TRY_CAST(date AS DATE) AS date,
               embedding::FLOAT[{DIM}] AS embedding
        FROM chunks_df
    """)
    print(con.sql("SELECT COUNT(*) AS chunks, COUNT(DISTINCT url) AS articles, "
                  "ROUND(AVG(LENGTH(text))) AS avg_chars, MAX(LENGTH(text)) AS max_chars "
                  "FROM news_chunks"))
    con.close()


if __name__ == "__main__":
    main()
