=================
UsernameToChatAPI
=================

This project aims to give telegram bot developers an easy way to get Chat objects for usernames. The documentation
for the API itself lies in textRoutes.

This project is very much in an early alpha phase and should not be used in production.

A running instance can be found at https://usernameToChatAPI.de

=====================
Run your own instance
=====================

All you need to do is change the api id and hash in api_keys.py, as well as LOG_ID in the log.py file. I recommend inserting
a joinchat link there. The first account you enter needs to be able to write there.
You also need to change the api keys, and you could change the owner insert in textRoutes.
Then install the requirements and run main :)

The first time you run main, the call will ask you for a phone number. This will be the telegram account used for getting
the user_id from telegram. You can add more then one account, for that, change the CLIENT constant in main.py. The more
accounts you enter, the better can the server mitigate FloodWait errors.

============
Contributing
============

Thanks for thinking about this. I use black and mypy for code quality, and I adhere to the CSI standard for commenting:
https://standards.mousepawmedia.com/csi.html. If you want to add something to this project, just open an issue and get
the ok first, I would hate for you to waste time if I think it doesn't fit.