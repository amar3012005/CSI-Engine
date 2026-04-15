import os
from tavily import TavilyClient

tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
res = tavily_client.extract(["https://www.bbc.co.uk/news/resources/idt-sh/death_of_the_nile"])
print(res.get("results")[0].keys() if "results" in res else res)
