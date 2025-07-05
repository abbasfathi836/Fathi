import telebot
from keep_alive import keep_alive

TOKEN = '7820797572:AAEjFbNe9Tzb9fPtcudAErA7Wm0yzZLd8hs'

bot = telebot.TeleBot(TOKEN)

keep_alive()

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, f"شما گفتید: {message.text}")

bot.infinity_polling()