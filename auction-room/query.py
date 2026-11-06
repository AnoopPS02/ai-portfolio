import duckdb
con = duckdb.connect("data/auction_room.duckdb")

#print(con.sql("SHOW TABLES"))

#print(con.sql("DESCRIBE deliveries"))

#print(con.sql("DESCRIBE matches"))

#print(con.sql("DESCRIBE players"))

print(con.sql("""
    SELECT match_id, innings_no, count(is_legal_ball) as legal_deliveries
    FROM deliveries
    WHERE not is_super_over
    AND is_legal_ball is True
    GROUP BY match_id, innings_no
    LIMIT 10
""").df().to_string())