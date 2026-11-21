import duckdb
con = duckdb.connect("data/auction_room.duckdb")
from auction_room.team_needs import get_team_needs

#print(con.sql("SHOW TABLES"))

#print(con.sql("DESCRIBE deliveries"))

#print(con.sql("DESCRIBE matches"))

#print(con.sql("DESCRIBE players"))


print(get_team_needs(con, "CSK"))