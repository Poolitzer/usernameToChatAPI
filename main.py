import asyncio
from functools import partial

from telethon import TelegramClient
from aiohttp import web, ClientSession
import ujson as json
from typing import TypedDict, TYPE_CHECKING

from checkURL import check_url
from resolveUsername import endpoint
from api_keys import api_id, api_hash
from log import send_counter
import textRoutes

if TYPE_CHECKING:
    from typing import Mapping

import logging

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", filename="log.log"
)
# This will be used to make requests to telegram's API
client = TelegramClient("session_0", api_id, api_hash)


# This is the type hinted layout of the temp storage, so mypy can use this to do its type checking
class Username(TypedDict):
    bio: str
    chat_id: int
    chat_type: str
    first_name: str
    last_name: str


# the cache is just this json file. With this and scraping the telegram website, we can do less requests to the API
# if the website and our temp storage are the same, we dont need to renew it with an API call
cache: "Mapping[str, Username]" = json.load(open("cache.json", "rb"))


# this creates a usable session. You only want to do this once in order to benefit from collection pooling
async def session_creator() -> ClientSession:
    return ClientSession()


# this saves the temp storage dict to the json file every hour. if that breaks nothing important is lost
async def save() -> None:
    # the while loop takes care that the saving never stops :D
    while True:
        # this opens the file for writing as a file
        with open("cache.json", "w") as outfile:
            # and here it gets dumped, with the indent of 4 and sorted keys, so its nice to look at
            json.dump(cache, outfile, indent=4, sort_keys=True)
        # and here this sleeps for an hour (60 minutes * 60 seconds
        await asyncio.sleep(60 * 60)


# this gets the event loop, in order for us to register/call functions in it
loop = asyncio.get_event_loop()
# first, we have to create the session, so we can pass it on later. Remember, you only want one
session = loop.run_until_complete(session_creator())

# the app is the initiated web application
app = web.Application()
# here we add the router to each URL we want to support. every URL gets passed the check function first, which make
# sure all expected parameters exists, and then makes sure the api_key is allowed, if it is present. Then it reroutes
# the request to the route_to function, and passes on cache, client, and session. I wasn't able to directly
# import it because of circular imports, and this is the reason I went with partial, maybe someone can improve this
# later
app.router.add_get(
    "/resolveUsername",
    partial(
        check_url,
        expected_parameters=["api_key", "username"],
        route_to=endpoint,
        client=client,
        cache=cache,
        session=session,
    ),
)

# these two handlers are text only, they don't need the checker
app.router.add_get("/", textRoutes.index)
app.router.add_get("/api_doc", textRoutes.api_documentation)

# the runner gets initiated
runner = web.AppRunner(app)
# and set up
loop.run_until_complete(runner.setup())
# this defines the site which is supposed to run
site = web.TCPSite(runner, host="localhost", port=1234)
# and here the site gets started
loop.run_until_complete(site.start())
# this connects the client to telegram
loop.run_until_complete(client.connect())
# this task sends a log for how many calls each api key did, every now and then (an hour right now
loop.create_task(send_counter(client))
# the save task gets created here
loop.create_task(save())
# and this is the final call which runs forever.
loop.run_forever()
