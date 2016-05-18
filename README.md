# simple_tornado_scraper
Toy Asyncronous webservice


## Supported REST calls 

| Api call   | method | parameters                                | description                                                   | example                                                        |
|------------|--------|-------------------------------------------|---------------------------------------------------------------|----------------------------------------------------------------|
| load_urls  | post   | A list of urls attached to request's body | Used to provide a list of website urls to extract titles from | curl-X POST --data "@filename" http://localhost:8080/load_urls |
| get_titles | get    |                                           | Returns a list of already extracted titles as JSON            | curl -X GET http://localhost:8080/get_titles                   |

## Response JSON
### Fields
- url - website url
- title - website title
- timestamp - extraction timestamp


### Example
    [
      {
        "url": "http://fornova.com/",
        "title": "Fornova - Home",
        "timestamp": "2016-05-30 15:10:00"
      },
      {
        "url": "http://goldenfeeds.com",
        "title": "GoldenFeeds is a global leader of e-commerce product information generation and marketing",
        "timestamp": "2016-05-30 15:11:30"
      }
    ]
    
    
## Additional
- Each website title must be extracted only once (use Redis caching).
- The results must be stored and reused when queried for again
- Website data must be requested asynchronously. Don't wait for a request to finish in order to start the next one.
