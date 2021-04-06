import asyncio
import sys
import traceback

from telethon import TelegramClient
from aiohttp import web

from api_keys import ALLOWED_KEYS

# this module is used to do some (for the time being quite intense) logging to a telegram channel


async def log_call(
    client: TelegramClient, username="", rg_traceback="", fw_traceback=""
) -> None:
    # this is the base string, which will get appended based on the difference calls
    string_to_send = ""
    if rg_traceback:
        # this tracebacks is when the regex for the site fails in one case, which only happens when the username is
        # invalid, or so I hope. This is to check this, if it triggers wrongly, we have to investigate further
        string_to_send += (
            "The excepted regex fail happened, with the username @"
            + username
            + " and the following traceback:\n```"
            + rg_traceback
            + "```"
        )
    elif fw_traceback:
        # the floodwait from telegram is likely going to limit this API a bit, so it gets its own error
        string_to_send += (
            "A FloodWait happened!!! With the username @"
            + username
            + " and the following traceback:\n```"
            + fw_traceback
            + "```"
        )
    # this gets send to a channel
    await client.send_message(1488052888, string_to_send)


# this counter is used to save how many calls are being done per API call
counter = {}


async def increase_counter(api_key: str) -> None:
    # here the name gets taken from the allowed keys dict
    name = ALLOWED_KEYS[api_key]
    # if its not present in the dict, add it here
    if name not in counter:
        counter[name] = 0
    # increase the counter, so it happened once more
    counter[name] += 1


async def send_counter(client: TelegramClient) -> None:
    # same logic as the cache save, which means each startup gets a message from this
    while True:
        # this is the base string, on that
        string_to_send = "This time, the following bots used these many calls:\n\n"
        # we append the counter per api key
        for name in counter:
            string_to_send += f"• {name}: {counter[name]}\n"
        # nice bye here
        string_to_send += "\nSee you again in an hour :)"
        # sending it
        await client.send_message(1488052888, string_to_send)
        # clearing the dict so we dont count twice
        counter.clear()
        # and sleeping for an hour
        await asyncio.sleep(60 * 60)


# the purpose of this decorator function will try to send errors to telegram when they happen
def exception_decorator(func):
    # this is an async wrap function
    async def wrap_func(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if isinstance(e, web.HTTPException):
                # if the error is an instance of the HTTP errors, this means I have raised them manually earlier, so
                # no need to panic. they have their own log calls anyway.
                return e
            # this catches every exception. now we have to get the initiated client from the params
            client = False
            for arg in args:
                # if the type of the unnamed args is TelegramClient, we found the client \o/
                if type(arg) == TelegramClient:
                    client = arg
                    break
            if not client:
                # if args didn't yield a client, it could be in kwargs, so we check. This requires all named params to
                # be client, and client can never not be TelegramClient, but that's fine.
                if "client" in kwargs:
                    client = kwargs["client"]
                else:
                    # if we don't have a client here, it doesn't exists, so we raise
                    raise
            # traceback.format_tb returns the usual python message about an exception, but as a
            # list of strings rather than a single string, so we have to join them together.
            tb_list = traceback.format_tb(sys.exc_info()[2])
            tb_string = "".join(tb_list)
            # now the string, telling the kind of error and where it happened
            string_to_send = (
                f"Oh no, an unexpected error happened, but at least I can tell you about it. The name is"
                f" `{e.__repr__()}`, the traceback:\n```" + tb_string + "```"
            )
            # sending it
            await client.send_message(1488052888, string_to_send)
            # and writing it to our logfile
            raise

    return wrap_func
