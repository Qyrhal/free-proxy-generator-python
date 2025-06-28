
__author__ = "Qyrhal"
__version__ = "0.1.0"
__liscense__ = "MIT"
__status__ = "Development"

"""
This project adheres to the GPL-3.0 License of the Proxlify Repository as this is original work and does not contain source code from the original repository, only the json output.

Utility to obtain and validate http proxies for use in HTTP requests. It is written to obtain data and manipulate it Asynchronously in order to increase performance and reduce waiting time. However this file can be modified to be synchronous if needed to reduce code complexity.

fetches a list of proxies from json file located at: https://github.com/proxifly/free-proxy-list?tab=readme-ov-file
Much credit for proxlify for providing the free proxy jsons

this utility will check the proxies in batches and cache the working ones for future use.

USAGE:
```python
    # in main.py or wherever you need to use the proxy utility, you can do the following:    

    from proxy import Proxy
    import asyncio


    async def test_get_proxy():
        proxy_generator = Proxy()
        proxy = await proxy_generator.get_proxy()
        print(f"Proxy: {proxy}")

    asyncio.run(test_get_proxy())
    
```

Time Complexity: TODO

Time Complexity Justification:

    Linear search through json list of proxies, testing each one until a working proxy is found or all have been tested.

"""
import os 
import aiohttp
import json
from dotenv import load_dotenv
import random 
import diskcache
from collections import deque  
import asyncio

load_dotenv()

class Proxy:

    def __init__(self, batch_size: int = 1000, cache_expiry: int = 60 * 60 * 24):
        self.cache = diskcache.Cache(os.path.join('cache', 'proxy_cache'))
        self.proxy_url: str = os.environ.get('PROXY_LIST_HTTP', None) # replace with proxy json url, for example "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/countries/US/data.json" for all US proxies
        self.batch_size = batch_size
        self.cache_expiry = cache_expiry

    async def get_proxy(self) -> str | None:
        """
        Returns a valid proxy URL for use in HTTP requests.

        params:
            batch_size (int): Number of proxies to test in a batch.
            cache_expiry (int): Time in seconds for which the cache is valid.
        
        returns:
            str | None: A working proxy URL or None if no working proxy is found.
        """

        if self.cache.get('working_proxy') is not None:
            cached_proxy = self.cache.get('working_proxy')
            print("Using cached proxy.")
            # check if the cached proxy is still valid
            async with aiohttp.ClientSession() as session:
                _, is_working = await self._test_single_proxy(session, cached_proxy)
                if is_working:
                    print("Cached proxy is working.")
                    return cached_proxy
                else:
                    print("Cached proxy is not working, fetching a new one.")
                    self.cache.delete('working_proxy')
            
        proxy = await self._fetch_proxy()
        return proxy

    async def _fetch_proxy(self) -> str | None:
        """
        fetch_proxy called from get_proxy, excecuted when the cache fails to return a working proxy.

        returns:
            str | None: A working proxy URL or None if no working proxy is found.
        """

        if self.proxy_url == None:
            print("No proxy URL provided.")
            return None
        
        async with aiohttp.ClientSession() as session:
            all_proxies = None
            proxy_list = []

            if self.cache.get('http_proxies_requested') is None:
                async with session.get(self.proxy_url) as response:
                    response_json = await response.json()

                    proxy_list = [
                        f"{proxy['proxy']}" for proxy in response_json 
                        if not ('172.67' in proxy['proxy'] or '172.64' in proxy['proxy'])
                        ] # there is cloudflare edge servers in the mix, therefore it will not work, thus filter, this took way too long to debug
                    
                    # Filter out known bad proxies
                    bad_proxies = self.cache.get('bad_proxies', set())
                    proxy_list = [proxy for proxy in proxy_list if proxy not in bad_proxies]

                    # if no proxies are found then deleete the cache
                    if len(proxy_list) == 0:
                        print("No valid proxies found, clearing cache.")
                        self.cache.delete('http_proxies_requested')
                        self.get_proxy()  # Retry to fetch proxies
                    
                    # Shuffle 
                    # random.shuffle(proxy_list)
                
                    all_proxies = deque(proxy_list[0:self.batch_size])
                    
                    # Cache the proxy list for future use
                    self.cache.set('http_proxies_requested', proxy_list, expire=self.cache_expiry)
            else:
                cached_proxies = self.cache.get('http_proxies_requested')
                bad_proxies = self.cache.get('bad_proxies', set())
                filtered_proxies = [proxy for proxy in cached_proxies if proxy not in bad_proxies]
                all_proxies = deque(filtered_proxies[0:self.batch_size])
                proxy_list = filtered_proxies

            print(f"Proxies found: {len(all_proxies)}/{len(proxy_list)}")

            max_attempts = min(self.batch_size, len(all_proxies)) # choose the minimum of batch size and available proxies to avoid overflow
            attempts = 0
            
            #test in batch size 
            if len(all_proxies) >= self.batch_size:
                proxy = await self._test_proxy_batch(all_proxies)
                if proxy:
                    return proxy


            while len(all_proxies) > 0 and attempts < max_attempts:

                proxy = all_proxies.popleft()  
                attempts += 1

                print(f"Testing proxy {attempts}/{max_attempts}: {proxy}")

                _ , is_working = await self._test_single_proxy(session, proxy)
                
                if is_working :
                    print(f"Proxy {proxy} is working.")
                    self.cache.set('working_proxy', proxy)
                    return proxy
                else:
                    print(f"Proxy {proxy} failed.")
                    self._cache_bad_proxy(proxy)

            print("Max attempts reached or no more proxies available.")
        return None

    async def _test_proxy_batch(self, proxy_list: list) -> str | None:
        """
        Test multiple proxies concurrently and return the first working one.
        """
        timeout = aiohttp.ClientTimeout(total=3) # timeout so it doesn't hang forever
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Create tasks without awaiting them
            tasks = [self._test_single_proxy(session, proxy) for proxy in proxy_list]
            
            # Use asyncio.as_completed to get results as they come in
            for coroutine in asyncio.as_completed(tasks):
                try:
                    proxy, is_working = await coroutine
                    if is_working:
                        print(f"Working proxy found: {proxy}")
                        self.cache.set('working_proxy', proxy)
                        return proxy
                    else:
                        # Cache the bad proxy so we don't test it again
                        self._cache_bad_proxy(proxy)
                except Exception as e:
                    continue
        return None
        
    async def _test_single_proxy(self, session: aiohttp.ClientSession, proxy: str) -> tuple[str, bool]:
        """
        Test a single proxy using the provided session and return proxy and result.
        """
        try:
            async with session.get('https://httpbin.org/ip', proxy=proxy) as response:
                if response.status == 200:
                    return proxy, True
        except Exception:
            pass
        
        return proxy, False
    
    def _cache_bad_proxy(self, bad_proxy: str) -> None:
        """
        Cache a non-working proxy so it won't be tested again.
        """
        bad_proxies = self.cache.get('bad_proxies', set())
        bad_proxies.add(bad_proxy)
        # Cache bad proxies permanently (no expiry)
        self.cache.set('bad_proxies', bad_proxies)
    

if __name__ == '__main__':
    import asyncio

    async def test_get_proxy():
        proxy_generator = Proxy()
        proxy = await proxy_generator.get_proxy()
        print(f"Proxy: {proxy}")

    asyncio.run(test_get_proxy())
