# mysql --user=root --password=password --host=$SCRAP_MYSQL_PORT_3306_TCP_ADDR --database=test < schema.sql
# python scraping.py --mysql-host=$SCRAP_MYSQL_PORT_3306_TCP_ADDR --redis-host=$SCRAP_REDIS_PORT_6379_TCP_ADDR
mysql --user=root --password=password --host=$MYSQL_HOST --database=test < schema.sql
python scraping.py --mysql-host=$MYSQL_HOST --redis-host=$REDIS_HOST
