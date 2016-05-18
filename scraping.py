import json
from time import strftime, gmtime, time

from tornado import gen, web, ioloop, queues, httpclient
from tornado.httpclient import HTTPError
from tornado.options import define, options
import tornado.options
import redis
import tormysql
import lxml.html
import logging

CREATE_TABLE_SQL = '''CREATE TABLE IF NOT EXISTS titles
    (url VARCHAR(255) PRIMARY KEY,
    title VARCHAR(255),
    timestamp INT)'''
ALTER_CHARACTER_SET = 'ALTER DATABASE CHARACTER SET =  "utf8"'
INSERT_URL_TITL_TIME_SQL = "INSERT INTO titles (url, title, timestamp) VALUES('{}','{}','{}')"
SELECT_URL = 'SELECT url FROM titles'

logging.basicConfig(level=logging.INFO, format="%(message)s")
define("nworkers", default=15, type=int, help="Number of coroutines")
define("mysql_host", default="172.17.0.3", help="blog database host")
define("mysql_maxcon", default=20, type=int, help="Maximum connections available from the connection pool")
define("mysql_user", default="root", help="mysql user")
define("mysql_password", default="password", help="mysql password")
define("mysql_db", default="test", help="mysql database you want to connect to")
define("redis_host", default='127.0.0.1', help='redis host ip or fqdn')
define("redis_port", default=6379, type=int, help='redis port')


class DBClient():
    """ Database client. Used throughout the app to operate MySQL.

    Even though using string substitution (like .format() and %) is not the best way
    to create queries, but this driver is one of the fastest because it supports native
    tornado Futures in yield expressions, so I choose speed prior to maintainability and
    security in this particular application.
    """
    database = None

    def __init__(self):
        self.pool = tormysql.ConnectionPool(
            max_connections=options.mysql_maxcon,  # max open connections
            idle_seconds=7200,  # conntion idle timeout time, 0 is not timeout
            wait_connection_timeout=3,  # wait connection timeout
            host=options.mysql_host,
            user=options.mysql_user,
            passwd=options.mysql_password,
            db=options.mysql_db,
            charset="utf8"
        )
        DBClient.database = self

        ioloop.IOLoop.instance().add_callback(self.connect)

    @classmethod
    def instance(cls):
        return cls.database

    @gen.coroutine
    def connect(self):
        """ Before using the driver we alter database charset and createing table

        """
        with (yield self.pool.Connection()) as conn:
            with conn.cursor() as cursor:
                yield cursor.execute(ALTER_CHARACTER_SET)
                yield cursor.execute(CREATE_TABLE_SQL)
            conn.commit()

    @gen.coroutine
    def send(self, query, params):
        """ Use this method to alter DB

        :param query: format string for query
        :param params: actual query parameters
        :return: None
        """
        with (yield self.pool.Connection()) as conn:
            try:
                with conn.cursor() as cursor:
                    yield cursor.execute(query.format(*params))

            except Exception as e:
                logging.exception(e)
                yield conn.rollback()

            else:
                yield conn.commit()

    @gen.coroutine
    def get(self, query, dry_output=False):
        """ Use this method to fetch data from db.
        To options are available: either to return row cursor output
        in form of tuple of tuples, or output as a list of dicts.

        :param query: (str) actual query to be executed
        :param dry_output: (bool) switch output style
        :return: If dry_output True - output tuple of tuples, otherwise list of dicts
        """
        with (yield self.pool.Connection()) as conn:
            with conn.cursor() as cursor:
                yield cursor.execute(query)
                data = rows = cursor.fetchall()
                cols = [x[0] for x in cursor.description]
        if not dry_output:
            data = []
            for row in rows:
                record = {}
                for prop, val in zip(cols, row):
                    record[prop] = val
                data.append(record)

        raise gen.Return(data)


class RedisClient():
    """ This is not just a redis client. The main purpose of this class is to fetch
    web pages, extract titles, handle data from POST request handlers and keep cache of
    fetched pages, so that we don't fetch the same page twice. As the advanced option
    we could limit redis cache size and handle the rule "fetch each page only once" by some other means

    """
    Q = queues.Queue()
    database = None

    def __init__(self):
        self.rs = redis.StrictRedis(host=options.redis_host, port=options.redis_port)
        self.fetching = 'fetching'
        self.fetched = 'fetched'
        self.rs.delete(self.fetching, self.fetched)

    @gen.coroutine
    def process_queue(self):
        """Here we are listening for incoming data from POST request handler.
        When there are some data to process this function checks the cache
        and calls get_title_from_url, which asynchronously fetch the page.
        At the end we push fetched data to DB

        :return: None
        """
        while True:
            current_url = yield self.__class__.Q.get()

            if self.rs.sismember(self.fetching, current_url):
                logging.info("'%s' is already fetched", current_url)
                return
            logging.info('fetching %s', current_url)
            self.rs.sadd(self.fetching, current_url)
            title = yield self.get_title_from_url(current_url)
            if not title:
                self.rs.srem(self.fetching, current_url)
                logging.warning("Title for '%s' wasn\'t fetch", current_url)
            else:
                self.rs.sadd(self.fetched, current_url)
                logging.info('%s %s %s', current_url, title, strftime("%Y-%m-%d %H:%M:%S", gmtime()))
                yield DBClient.instance().send(INSERT_URL_TITL_TIME_SQL,
                                               (current_url, title, int(time())))

    @gen.coroutine
    def get_title_from_url(self, url):
        """ Asynchronously downloading the page.
        At the begging I specify the option:
         httpclient.AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
        This makes AsyncHTTPClient become truly async by using async DBS resolver.
        In order to use it you need pycurl and libcurl to be installed.
        I use lxml to parse html page because it quicker then BeautifulSoup (it seems to be quicker)

        """
        try:
            response = yield httpclient.AsyncHTTPClient().fetch(url)
            logging.info('fetched %s', url)

            encoded = response.body.encode() if isinstance(response.body, str) \
                else response.body
            tree = lxml.html.fromstring(encoded)
            title = tree.find('.//title').text
        except Exception as e:
            logging.exception('Exception: %s %s', e, url)
            raise gen.Return('')

        raise gen.Return(title)


class BaseHandler(web.RequestHandler):
    """ Not really necessary class. It can be used in order to extend base functionality
    of all specific request handlers. Now it provides quick access to database object,
    although it is available in singleton manner.

    """
    def initialize(self, database):
        self.db = database


class GetTitlesHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        self.set_header("Content-Type", 'application/json; charset="utf-8"')
        data = yield self.db.get('SELECT * FROM titles')
        self.write(json.dumps(data))


class LoadUrlsHandler(BaseHandler):
    @gen.coroutine
    def post(self):
        """
        Expecting to get json list as a POST parameter.
        Otherwise - Bad request.
        :return:
        """
        if self.request.headers.get('Content-Type').startswith('application/json'):
            jsonstr = self.request.body if isinstance(self.request.body, str) \
                else self.request.body.decode(errors='ignore')

            loaded = json.loads(jsonstr)
            if isinstance(loaded, list):
                for item in set(loaded):
                    yield RedisClient.Q.put(item)
                    logging.info("Put %s", item)
            else:
                raise HTTPError(400)
        else:
            raise HTTPError(400)


if __name__ == "__main__":
    # In order to handle 100000 fetch request I would place this instance behind nginx load balancer
    # or even run another instance, which will pass all parse requests to rabbit-mq using cyclone.
    #
    # In order to fetch 10 records instead of 1 I would rewrite get_title_by_url function
    # to be something like get_arbitrary_records_from_url(url, list_of_tags_to_extract)
    # Also I would need some convenient tool to do database schema alteration according to my needs

    tornado.options.parse_command_line()
    try:
        httpclient.AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
    except:
        logging.error("Please install pycurl and compile libcurl on your computer in order to use async dns resolver")
        pass

    db = DBClient()
    workers = [RedisClient() for _ in range(options.nworkers)]
    for worker in workers:
        ioloop.IOLoop.instance().add_callback(worker.process_queue)

    application = web.Application([
        (r'/load_urls', LoadUrlsHandler, dict(database=db)),
        (r'/get_titles', GetTitlesHandler, dict(database=db)),
    ], debug=True)

    application.listen(8888)
    try:
        ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        ioloop.IOLoop.instance().stop()
