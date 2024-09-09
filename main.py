import os
import openai
from flask import Flask, request
from telebot import TeleBot, types
from redis import Redis, ConnectionPool
from markdownmail import MarkdownMail
import logging
import time
import ast
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
pool = ConnectionPool.from_url(redis_url)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
URL = os.environ.get("URL")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
TO_EMAIL = ast.literal_eval(os.environ.get("TO_EMAIL"))

bot = TeleBot(BOT_TOKEN, threaded=True)
bot.remove_webhook()
time.sleep(1)
bot.set_webhook(url=f"{URL}/{WEBHOOK_SECRET}")
r = Redis(connection_pool=pool)


def send_email(subject, message, to_email):
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = int(os.environ.get("SMTP_PORT"))
    smtp_login = os.environ.get("SMTP_LOGIN")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("FROM_EMAIL")

    from_name = "SOAP Bot"
    from_addr = f"{from_name} <{from_email}>"

    email = MarkdownMail(
        from_addr=from_addr, to_addr=to_email, subject=subject, content=message
    )
    try:
        email.send(
            smtp_server, login=smtp_login, password=smtp_password, port=smtp_port
        )
        print("Email sent successfully")

    except Exception as e:
        print("Error sending email:", e)


@bot.message_handler(commands=["start", "restart"])
def start(message):
    """Handle /start and /restart commands."""
    try:
        message_to_send = "Hello! Please enter the child's name"
        
        r.set(message.from_user.id, str({}))

        msg = bot.send_message(message.chat.id, message_to_send, parse_mode="Markdown")
        bot.register_next_step_handler(msg, get_child_name)

    except Exception as e:
        logger.error(f"Error starting the bot: {e}")

def get_child_name(message):
    """Handler to get and store the child's name."""
    try:
        user_data = {"name": message.text}
        r.set(message.from_user.id, str(user_data))
        
        message_to_send = "Thanks! Now, please enter the child's age (e.g., 2 years, 3 months)."
        msg = bot.send_message(message.chat.id, message_to_send, parse_mode="Markdown")
        bot.register_next_step_handler(msg, get_child_age)

    except Exception as e:
        logger.error(f"Error getting child name: {e}")


def get_age_from_gpt(message):
    try:
        openai_client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You have to strictly respond with a number referring to the age in months"
                                "Do not add any other text to the response."
                                "If the unit is not strictly mention, it is referring to years and convert it to months"
                                "If it is not possible to extract the age, return 'None'"
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": message
                        }
                    ],
                },
            ],
            temperature=0.7,
        )
        report = response.choices[0].message.content
        return report
    except Exception as e:
        logger.error(f"Error generating age from chatGPT: {e}")
        return None


def age_less_than_1(message):
    """Handler for children under 1 month old."""
    try:
        msg = bot.send_message(
            message.chat.id,
            "We are sorry, but our system only supports children atleast 1 month old.",
        )
    except Exception as e:
        logger.error(f"Error handling age less than 1: {e}")


def age_less_than_3(message):
    """Handler for children under 3 months old."""
    try:
        pass
    except Exception as e:
        logger.error(f"Error handling age less than 3: {e}")


def age_less_than_6(message):
    """Handler for children under 6 months old."""
    try:
        pass
    except Exception as e:
        logger.error(f"Error handling age less than 6: {e}")


def age_less_than_9(message):
    """Handler for children under 9 months old."""
    try:
        pass
    except Exception as e:
        logger.error(f"Error handling age less than 9: {e}")


def age_less_than_12(message):
    """Handler for children under 12 months old."""
    try:
        pass
    except Exception as e:
        logger.error(f"Error handling age less than 12: {e}")


def age_less_than_18(message):
    """Handler for children under 18 months old."""
    try:
        pass
    except Exception as e:
        logger.error(f"Error handling age less than 18: {e}")


def age_less_than_24(message):
    """Handler for children under 24 months old."""
    try:
        pass
    except Exception as e:
        logger.error(f"Error handling age less than 24: {e}")


def age_less_than_36(message):
    """Handler for children under 36 months old."""
    try:
        pass
    except Exception as e:
        logger.error(f"Error handling age less than 36: {e}")


def age_less_than_48(message):
    """Handler for children under 48 months old."""
    try:
        pass
    except Exception as e:
        logger.error(f"Error handling age less than 48: {e}")


def age_less_than_60(message):
    """Handler for children under 60 months old."""
    try:
        pass
    except Exception as e:
        logger.error(f"Error handling age less than 60: {e}")


def age_more_than_60(message):
    """Handler for children over 5 years old."""
    try:
        msg = bot.send_message(
            message.chat.id,
            "We are sorry, but our system only supports children up to 5 years old.",
        )

        markup = types.InlineKeyboardMarkup()
        restart_button = types.InlineKeyboardButton("Restart", callback_data="restart")
        markup.add(restart_button)

        bot.send_message(message.chat.id, "You can restart the process.", reply_markup=markup)

    except Exception as e:
        logger.error(f"Error handling age more than 60: {e}")


@bot.callback_query_handler(func=lambda call: call.data == "restart")
def handle_restart_callback(call):
    """Callback handler for the restart button."""
    try:
        start(call.message)
    except Exception as e:
        logger.error(f"Error handling restart callback: {e}")


def get_child_age(message):
    """Handler to get and store the child's age."""
    try:
        age = int(get_age_from_gpt(message.text))
        user_data = ast.literal_eval(r.get(message.from_user.id).decode("utf-8"))
        user_data["age"] = age
        
        r.set(message.from_user.id, str(user_data))
        bot.send_message(message.chat.id, f"Child's name and age saved: {user_data}", parse_mode="Markdown")

        if age < 1:
            bot.register_next_step_handler(msg, age_less_than_1)
        elif age <= 3:
            bot.register_next_step_handler(msg, age_less_than_3)
        elif age <= 6:
            bot.register_next_step_handler(msg, age_less_than_6)
        elif age <= 9:
            bot.register_next_step_handler(msg, age_less_than_9)
        elif age <= 12:
            bot.register_next_step_handler(msg, age_less_than_12)
        elif age <= 18:
            bot.register_next_step_handler(msg, age_less_than_18)
        elif age <= 24:
            bot.register_next_step_handler(msg, age_less_than_24)
        elif age <= 36:
            bot.register_next_step_handler(msg, age_less_than_36)
        elif age <= 48:
            bot.register_next_step_handler(msg, age_less_than_48)   
        elif age <= 60:
            bot.register_next_step_handler(msg, age_less_than_60)   
        else:
            bot.register_next_step_handler(msg, age_more_than_60)
    
    except ValueError:
        msg = bot.send_message(message.chat.id, "Invalid age. Please enter a valid age.")
        bot.register_next_step_handler(msg, get_child_age)


@app.route(f"/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    """Webhook to handle incoming updates from Telegram."""
    update = types.Update.de_json(request.data.decode("utf8"))
    bot.process_new_updates([update])
    return "ok", 200


if __name__ == "__main__":
    app.run()
