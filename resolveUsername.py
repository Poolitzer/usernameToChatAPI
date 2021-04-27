import html
import re
import traceback
from typing import Generator, TypedDict, TYPE_CHECKING
import sys
import asyncio

from aiohttp import web, web_response
from bs4 import BeautifulSoup
from bs4.element import Tag, NavigableString
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon import errors

# these calls are temporarily to monitor the behaviour of the api
from log import log_call, exception_decorator, increase_counter

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from telethon import TelegramClient
    from typing import Tuple, Union, Literal, MutableMapping, Mapping

    from main import Username

# this is a dictionary which will hold clients which are in a floodwait, so we can use other ones
flood_wait: "MutableMapping[str, Union[bool, int]]" = {}

# usernames which are banned on iOS devices but actual fine chats. the website might not work for them, so I hardcode
# them here when I encounter them and do not try the website for them later on. I have to map the names to their chat
# type because otherwise we get the type from the website
COPYRIGHT_USERNAMES: "Mapping[str, str]" = {"utubebot": "private"}


class RegexFailedError(Exception):
    # this custom error class is just used to pass the expected regex fail when an username is invalid to the higher
    # function. this should avoid swallowing an different IndexError
    pass


def get_text(tag: "Tag") -> str:
    """
    This function only replaces <br> tags with \n right now. If more issues with the website bio vs API bio show up,
    this can be used to battle them. This code is taken with much thanks from
    https://stackoverflow.com/a/66835172/12692773, published by Vijay Hebbar[https://github.com/vjhebbar].
    """

    def _get_text(tag2: Tag) -> Generator:
        # this iterates through all provided tags
        for child in tag2.children:
            # if the child is a Tag, it gets processed, otherwise only the text content gets yielded
            if type(child) is Tag:
                # here, br is replaced or it gets passed on to the function itself
                yield from ["\n"] if child.name == "br" else _get_text(child)
            elif type(child) is NavigableString:
                yield child.string

    # and the content gets squashed in one string
    return "".join(_get_text(tag))


async def website(username: str, session: "ClientSession") -> "Tuple[str, str, str]":
    """
    This function parses the website and returns the three information which one can get from it
    """
    # this sets together the url and "awaits" the result
    # Reminder: If we ever get limited from telegram to call this website, we should deal with this here
    async with session.get("https://t.me/" + username) as response:
        # the whole website is put in one string here for further processing
        html_string = await response.text()
        # the next lines take care of the biography, if it exists. I have to use BS4 to parse its content properly
        parsed_html = BeautifulSoup(html_string, features="html.parser")
        bio_div = parsed_html.body.find("div", attrs={"class": "tgme_page_description"})
        if bio_div:
            bio = get_text(bio_div)
        else:
            bio = ""
        # this gets the name (set together from first_name + " " + last_name or just the title) from the chat
        names = html.unescape(
            re.findall('<meta property="og:title" content="(.*)">', html_string)[0]
        )
        # this is used to determine the chat type. I am pretty sure I had an example where the first regex was necessary
        # , though I am unable to find it right now. The second one is the usual one though.
        result = re.findall(
            '<div class="tgme_page_extra">\n {2}(.*)\n</div>|'
            '<div class="tgme_page_extra">(.*)</div>',
            html_string,
        )
        # this sets the extra variable to the result, depending on which regex triggered it
        # if the regex fails, the username doesn't exists, or at least I hope so. This is also closely monitored for now
        try:
            if result[0][0]:
                extra = result[0][0]
            else:
                extra = result[0][1]
        except IndexError:
            # this is a bit of a hacky way to tell the code later that the username is invalid
            raise RegexFailedError
        # now we can determine the type depending on the extra. its going to be the username for private chats,
        # the members count for channels, the members count + online members for supergroups.
        if extra.startswith("@"):
            chat_type = "private"
        elif "online" in extra:
            chat_type = "supergroup"
        else:
            chat_type = "channel"
        # and we return the three important information as a tuple
        return names, bio, chat_type


# type hint for the response, same way telegram returns it. Non existing keys are dropped, that's why total is false
class ResponseData(TypedDict, total=False):
    id: int
    type: str
    username: str
    first_name: str
    last_name: str
    title: str
    bio: str
    description: str


# and the one from above are nested into this
class ResponseDict(TypedDict):
    ok: bool
    result: ResponseData


# this creates the response dict
def create_response(username: str, info_dict: "Username") -> ResponseDict:
    # this basic construct is the same for private + channel chats, so we define it here
    data: ResponseDict = {
        "ok": True,
        "result": {
            "id": info_dict["chat_id"],
            "type": info_dict["chat_type"],
            "username": username,
        },
    }
    # now the difference between private and channels. the if clauses are used to simulate how telegram builds the json,
    # only showing the keys which have information.
    if info_dict["chat_type"] == "private":
        data["result"]["first_name"] = info_dict["first_name"]
        if info_dict["last_name"]:
            data["result"]["last_name"] = info_dict["last_name"]
        if info_dict["bio"]:
            data["result"]["bio"] = info_dict["bio"]
    else:
        # the bot api has the prepending -100 for supergroups/channels, so we add it here
        data["result"]["id"] = int("-100" + str(data["result"]["id"]))
        data["result"]["title"] = info_dict["first_name"]
        if info_dict["bio"]:
            data["result"]["description"] = info_dict["bio"]
    return data


def create_error_response(code, description, retry_after=None):
    data = {
        "ok": False,
        "error_code": code,
        "description": description,
    }
    if retry_after:
        data["retry_after"] = retry_after
    return data


# the exception decorator will try to send a message to telegram telling me about an error here
@exception_decorator
async def endpoint(
    request: web.Request,
    clients: "list[TelegramClient]",
    cache: "MutableMapping[str, Username]",
    session: "ClientSession",
) -> web.Response:
    # this is just here so mypy is happy. It could stay as the first client, but could change later, that happens in the
    # for loop
    # this client variable will be set to the client if they aren't all hit with a flood error
    client: "TelegramClient" = clients[0]
    # from the available clients, we select one
    for potential_client in clients:
        # noinspection PyUnresolvedReferences
        # the above line is so PyCharm doesn't complain over a valid access. We use the filename as a unique
        # name for the client, which should make it easy to add more clients in the future
        client_name = potential_client.session.filename
        # this checks if the client is not in flood wait, then we select it
        if client_name not in flood_wait:
            client = potential_client
            break
        elif potential_client == clients[-1]:
            # this logic is True if all clients are hit by a floodwait error. Currently, this timer
            # is updated every second, so we are not missing time. Depending on the limits we hit and the strain this
            # countdown (especially with several clients) puts on our system we might need to change this. The logic
            # behind this is good though: The client_name is set to False if no flood, or a number if its flood
            # the response mimics telegrams error responses. We pass the lowest floodwait as error.
            return web.json_response(
                data=create_error_response(
                    429, "Telegram forces us to wait", flood_wait[min(flood_wait)]
                ),
                status=429,
            )
    # this gets the username from the url query
    user_name = request.rel_url.query["username"]
    # if the submitted username starts with an @, it is removed here. not having it later is exactly how telegram
    # returns usernames, so this is fine
    if user_name.startswith("@"):
        user_name = user_name[1:]
    # this is set to the cached data, if it exists, so we can use it to compare it to the website
    known: Union[Literal[False], "Username"] = False
    if user_name.lower() in cache:
        # setting it to lower avoids issues with the case
        known = cache[user_name.lower()]
    # this check does not try to parse websites for usernames which exist but generate a wrong website.
    if user_name.lower() not in COPYRIGHT_USERNAMES:
        # this subscribes the tuple result to three unique variables
        try:
            names, bio, chat_type = await website(user_name, session=session)
        except RegexFailedError:
            # if that error is raised, this means the username is invalid (or so I hope), so we raise a BadRequest
            # error.
            # we also log this (and the traceback) to a channel so we can do close monitoring for now
            # traceback.format_tb returns the usual python message about an exception, but as a
            # list of strings rather than a single string, so we have to join them together. We use the first client
            # to log
            # because that is the one which we require to be in the log chat
            tb_list = traceback.format_tb(sys.exc_info()[2])
            tb_string = "".join(tb_list)
            await log_call(clients[0], user_name, rg_traceback=tb_string)
            # this gives the error to the user the same way telegram does
            return web.json_response(
                data=create_error_response(400, "Bad Request: chat not found"),
                status=400,
            )
        # known is set to the cached data, so if we have data here, we can use it
        if known:
            known_names = known["first_name"]
            # names is the result of the website. it combines first and last name from a user with a space, so we
            # do it here as well. for chats, we have their title set as first_name and no last_name/space issue
            if known["last_name"]:
                known_names += " " + known["last_name"]
            # if all three properties are the same, we assume the chat_id is as well, and use our cached values. This
            # could lead to an issue if only the id changes, but all other properties stay the same. This will be
            # closely monitored for the time being. But using the cache should avoid hitting the flood wait too much
            if (
                names == known_names
                and bio == known["bio"]
                and chat_type == known["chat_type"]
            ):
                # this function call increases a counter for how many requests each api key did
                await increase_counter(request.rel_url.query["api_key"], "cache")
                # here we pass the cached data to the dict creation and then return the json response as response
                data = create_response(user_name, known)
                return web.json_response(data=data)
    else:
        # we set chat type from the hardcoded dict, because we need it to call the correct api method
        chat_type = COPYRIGHT_USERNAMES[user_name.lower()]
    # if we reached this part of the code, we either don't have cached values, or they are out of date, or we couldn't
    # use the website to verify them. So we get new
    # ones from telegram at this point. This is its own function because we need it to be recursive to switch clients
    potential_error = await get_chat_from_api(
        client, chat_type, user_name, clients, cache
    )
    # a floodwait response could be returned so we check for it here
    if type(potential_error) == web_response.Response:
        # this needs to be returned to the server so we return
        return potential_error
    # this function call increases a counter for how many requests each api key did
    await increase_counter(request.rel_url.query["api_key"], "api_call")
    # here it is send to the dict creation function, and the result is given as a web response. Getting it from cache
    # might be a bit resource wasting, but this is python, so who cares
    data = create_response(user_name, cache[user_name.lower()])
    return web.json_response(data=data)


async def flood_runs_out(client: str) -> None:
    # this is the countdown to update the flood wait time. It is set to one second right now, this can be
    # changed/made smarter later.
    while flood_wait[client] >= 0:
        await asyncio.sleep(10)
        # subtracting one second from the time we have to wait because we slept one second
        flood_wait[client] -= 10
    # if wait is 0 or less, we set it to false, and then break the loop.
    del flood_wait[client]


async def get_chat_from_api(
    client: "TelegramClient",
    chat_type: str,
    user_name: str,
    clients: "list[TelegramClient]",
    cache: "MutableMapping[str, Username]",
):
    # this whole function is recursive. It will call itself if one client reaches a FloodWaitError
    try:
        if chat_type == "private":
            # noinspection PyTypeChecker
            # the above line is so PyCharm doesn't complain about user_name being the username, telethon is totally fine
            # with this. We have to get the full user/chat in order to get the bio of the chat
            full = await client(GetFullUserRequest(user_name))
        else:
            # noinspection PyTypeChecker
            # same as above, just a slightly different api call
            full = await client(GetFullChannelRequest(user_name))
    except errors.FloodWaitError as e:
        # now we can check if there are other clients left we can try
        # since we have to do the exact same logic for the non private chat, I moved it to it's own function, see
        # below
        await flood_error(client, user_name, e, clients)
        # now we can check if there are more clients available to instead do the function call
        # how this for loop works, see above
        for potential_client in clients:
            # noinspection PyUnresolvedReferences
            client_name = potential_client.session.filename
            # this checks if the client is not in flood wait, then we select it
            if client_name not in flood_wait:
                return await get_chat_from_api(
                    potential_client, chat_type, user_name, clients, cache
                )
        # If we reached this part of the code, it means all clients are sadly hit with a FloodWait. We return the lowest
        # and go on with our life
        # this also resolves in a specific log call
        await log_call(clients[0], user_name, all_clients_hit=str(flood_wait))
        return web.json_response(
            create_error_response(429, "Telegram forces us to wait", e.seconds),
            status=429,
        )
    except ValueError as e:
        # the ValueError happens when the API returns that the username is unknown. This could happen with the hardcoded
        # values, or just with a very badly timed username change
        await log_call(clients[0], user_name, username_not_found=e.args[0])
        # we return the bad request to the user
        return web.json_response(
            data=create_error_response(400, "Bad Request: chat not found"),
            status=400,
        )
    # and we write it to the cache. We loose capitalization of the username here, but that doesn't matter, since
    # they are case insensitive. We always return the username they put in the URL anyway
    if chat_type == "private":
        cache[user_name.lower()] = {
            "first_name": full.user.first_name,
            "last_name": full.user.last_name,
            "bio": full.about,
            "chat_type": chat_type,
            "chat_id": full.user.id,
        }
    # we don't have a last_name in other chats, so we set it to an empty string. Also, the return type is slightly
    # different
    else:
        cache[user_name.lower()] = {
            "first_name": full.chats[0].title,
            "last_name": "",
            "bio": full.full_chat.about,
            "chat_type": chat_type,
            "chat_id": full.chats[0].id,
        }


async def flood_error(
    client: "TelegramClient",
    user_name: str,
    e: errors.FloodWaitError,
    clients: "list[TelegramClient]",
):
    # noinspection PyUnresolvedReferences
    # again, the above line is so PyCharm doesn't complain over a valid access. We use the filename as a unique
    # name for the client, which should make it easy to add more clients in the future
    client_name = client.session.filename
    # we set this to True so we don't spam telegram any more then needed
    flood_wait[client_name] = e.seconds
    # this runs the function in the background
    asyncio.create_task(flood_runs_out(client_name))
    # and we tell our users about this. Maybe we should provide a better way to access the seconds value, I will
    # think about this later
    tb_list = traceback.format_tb(sys.exc_info()[2])
    tb_string = "".join(tb_list)
    # we add the seconds we wait for so we can make decisions based on this
    tb_string += "\n\nWaiting for " + str(e.seconds) + " seconds."
    await log_call(clients[0], user_name, fw_traceback=tb_string)
