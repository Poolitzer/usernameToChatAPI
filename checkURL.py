from aiohttp import web
from typing import TYPE_CHECKING

from log import increase_counter
from api_keys import ALLOWED_KEYS
from resolveUsername import create_error_response

if TYPE_CHECKING:
    from typing import Mapping, Callable, Awaitable
    from telethon import TelegramClient
    from main import Username
    from aiohttp import ClientSession


# This is a generic url checker. It is a bit over the top for the on request this projects supports so far, but it will
# make it very easy to extend it later on.
async def check_url(
    request: web.Request,
    expected_parameters: list,
    route_to: "Callable[[web.Request, TelegramClient, Mapping[str, Username], ClientSession],"
    "Awaitable[web.Response]]",
    client: "TelegramClient",
    cache: "Mapping[str, Username]",
    session: "ClientSession",
) -> web.Response:
    # this loop goes through all the expected parameters and check if they exists in the URL. If they do not, a Bad
    # Request is thrown, providing the missing parameter
    for parameter in expected_parameters:
        if parameter not in request.rel_url.query:
            error_string = parameter + " is missing."
            return web.json_response(
                data=create_error_response(400, error_string), status=400
            )
    # if the api_key parameter is present, this part checks if the key is present in the list of keys. If it is not,
    # an Unauthorized error is thrown
    if "api_key" in expected_parameters:
        if request.rel_url.query["api_key"] not in ALLOWED_KEYS:
            error_string = "Unauthorized"
            return web.json_response(
                data=create_error_response(401, error_string), status=400
            )
    # this function call increases a counter for how many requests each api key did
    await increase_counter(request.rel_url.query["api_key"])
    # now the function which is supposed to handle the request gets the request, next to the three initiated objects,
    # which they can not import because of circular imports
    return await route_to(request, client, cache, session)
