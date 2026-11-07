import duckdb
con = duckdb.connect("data/auction_room.duckdb")

#print(con.sql("SHOW TABLES"))

#print(con.sql("DESCRIBE deliveries"))

#print(con.sql("DESCRIBE matches"))

#print(con.sql("DESCRIBE players"))


print(con.sql("""
    select * from batting_season
    where season = 2016
    order by runs desc
    limit 10
""").df().to_string())