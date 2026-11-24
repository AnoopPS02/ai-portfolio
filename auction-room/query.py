import duckdb
con = duckdb.connect("data/auction_room.duckdb")
from auction_room.team_needs import get_team_needs
from auction_room.news import search_news_tool

#print(con.sql("SHOW TABLES"))

#print(con.sql("DESCRIBE deliveries"))

#print(con.sql("DESCRIBE matches"))

#print(con.sql("DESCRIBE players"))


#print(get_team_needs(con, "CSK"))

print(search_news_tool(con, "why was Mitchell Starc released"))