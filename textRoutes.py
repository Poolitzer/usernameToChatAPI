from aiohttp import web

# these functions just return strings. It might make sense to move them to their own folder later and turn them to plain
# html files.


async def index(request: web.Request):
    owner_insert = (
        "Since you discovered this text on the https://usernameToChatAPI.de domain, https://t.me/poolitzer (me \o/)"
        " is/am the owner of this instance. I am willing to give you a key, just PM me on Telegram, tell me how "
        "many requests per time you are going to do roughly and I will see how it fits in the correct project "
        "utilisation."
    )
    string = (
        "Hello there.\n\nYou stumbled over a running instance of the usernameToChatAPI project. The purpose of this "
        "API "
        "is to provide a way for Telegram Bots which are using the HTTP API to resolve usernames to chat objects. This "
        "mitigates the need for these bots to write their own interaction with the foreign MTProto API. Instead, they "
        "can use this API and profit from less setup and known objects. The project is Open Source and can be found at "
        "https://github.com/Poolitzer/usernameToChatAPI. It is licensed under GNU GPLv3.\n\nIf you are interested to "
        f"integrate this API in your project, amazing. You will need an api key to use this project. {owner_insert}\n\n"
        f"Once you have the API key, head over to {request.url.origin()}/api_doc to check out the (very small) "
        f"documentation for this API.\n\nThe great python-telegram-bot library has a contrib submodule, "
        f"which provides a "
        f"neat integration of this API in the library. Check it out at https://github.com/python-telegram-bot/"
        f"ptbcontrib/tree/main/ptbcontrib/username_to_chat_api."
    )
    return web.Response(text=string)


async def api_documentation(_: web.Request):
    string = (
        "This document represents the whole documentation of the usernameToChatAPI.\n\nThere is currently one "
        "supported GET request: resolveUsername. This method takes two parameters, api_key and username. Submit them "
        "via an URL query string. If you want a different way of submitting these parameters, open an issue about it, "
        "and we will find a way. The api_key is case sensitive, the username can be passed with or without a leading @."
        "\n\nThe successful call will result in a json response, mimicking the getChat response from "
        "the telegram API for the respective types: https://core.telegram.org/bots/api#chat. Bio/description are "
        "passed if present as well. Photo is not passed, this wouldn't make sense.\n\nError handling is the same as "
        "telegram does it. Expected errors are 400, when the chat is not found or parameters are missing, 401, when "
        "the API key is wrong, and 429, if the API is hit with a "
        "flood wait error. The retry_after attribute is present in this case so you can wait that long before making "
        "more requests."
    )
    return web.Response(text=string)
