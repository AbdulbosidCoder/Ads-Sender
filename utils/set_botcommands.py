from aiogram import types

commands = [
    types.BotCommand(command='start', description="Botni ishga tushirish"),
    types.BotCommand(command='help', description="Botni ishlashini tushuntiradi"),
    types.BotCommand(command="token", description="ChatGpt ni tokenini almashtirish"),
    types.BotCommand(command="topic_create", description="Create Enter Topics"),
    types.BotCommand(command="topic_delete", description="/topic_delete <topic_id> Delete a topic from DB.Example: /topic_delete 12"),
    types.BotCommand(command="my_groups", description="Return the group which you add us")
]