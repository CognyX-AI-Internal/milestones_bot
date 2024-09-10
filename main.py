import os
import openai
from flask import Flask, request
from telebot import TeleBot, types
from redis import Redis, ConnectionPool
from datetime import datetime
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
# bot.remove_webhook()
# time.sleep(1)
# bot.set_webhook(url=f"{URL}/{WEBHOOK_SECRET}")
r = Redis(connection_pool=pool)


AGE_GROUPS = [3, 6, 9, 12, 18, 24, 36, 48, 60]

with open("checklist_options.json", "r") as f:
    checklist_options = ast.literal_eval(f.read())
checklist_options = {int(k): v for k, v in checklist_options.items()}

with open("suggestions.json", "r") as f:
    suggestions = ast.literal_eval(f.read())
suggestions = {int(k): v for k, v in suggestions.items()}


def send_email(subject, message, to_email):
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = int(os.environ.get("SMTP_PORT"))
    smtp_login = os.environ.get("SMTP_LOGIN")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("FROM_EMAIL")

    from_name = "Milestones Bot"
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


def get_dev_age_from_gpt(message, age_group):
    try:
        openai_client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

        age_group_idx = AGE_GROUPS.index(age_group)
        prev_age_group = AGE_GROUPS[age_group_idx - 1] if age_group_idx > 0 else None
        prev_age_group_2 = AGE_GROUPS[age_group_idx - 2] if age_group_idx > 1 else None
        prev_age_group_3 = AGE_GROUPS[age_group_idx - 3] if age_group_idx > 2 else None 
        # print(checklist_options.get(p))

        system_content = (
            f"You have to strictly respond with a number referring to the age in months.\n"
            f"Do not add any other text to the response.\n"
            # f"These are the expected capabilities of a {prev_age_group_3} months old: {str(checklist_options.get(prev_age_group_3, 'N/A'))}\n"
            f"These are the expected milestones of a {prev_age_group_2} months old: {str(checklist_options.get(prev_age_group_2, 'N/A'))}\n"
            f"These are the expected milestones of a {prev_age_group} months old: {str(checklist_options.get(prev_age_group, 'N/A'))}\n"
            f"These are the expected milestones of a {age_group} months old: {str(checklist_options.get(age_group, 'N/A'))}\n"
            f"You will receive a list of milestones and a corresponding boolean, showing whether the patient is successfully able to do them.\n"
            f"If the milestones are much more advanced than the previous ones it's known the previous milestones are met. E.g. a child who is talking most likely babbled as a baby."
            f"Return an estimated development age for the child in months.\n"
            f"If the estimated age is less than 3 months, return 0."
        )

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": message
                },
            ],
            temperature=0.7,
        )
        report = response.choices[0].message.content
        return int(report)
    except Exception as e:
        logger.error(f"Error generating development age from chatGPT: {e}")
        return None


def generate_recommendations(message, age_group):
    try:
        openai_client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
        )

        system_content = (
            "You will receive a list of tuples, where the the True/False value indicates whether the child has hit a milestone or not"
            "Return a list of recommendations so that the user can improve"
            "Do not return recommendations where the user has already hit a milestone"
            f"Strictly stick to the following recommendations {str(suggestions[age_group])}"
            "The recommendations should be in Markdown format"
        )

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": message
                },
            ],
            temperature=0.7,
        )
        report = response.choices[0].message.content
        return report
    except Exception as e:
        logger.error(f"Error generating recommendations from chatGPT: {e}")
        return None



def get_word_age(dev_age):
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
                                "You have to strictly respond with age"
                                "Do not add any other text to the response."
                                "You will recieve an age in months you have to reply in this format: years, months"
                                "Ignore the years part if the input is less than 12"
                                "For example 15: 1 year, 3 months"
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": str(dev_age)
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

def create_checklist_markup(user_id, checklist_options):
    """Creates a checklist markup with current selections."""
    user_data = ast.literal_eval(r.get(user_id).decode("utf-8"))
    
    if 'checklist' not in user_data:
        user_data['checklist'] = [False] * len(checklist_options)
        r.set(user_id, str(user_data))

    markup = types.InlineKeyboardMarkup()
    for idx, option in enumerate(checklist_options):
        status = "✅" if user_data['checklist'][idx] else "⬜️"
        option_text = f"{status} {option}".ljust(73, ' ')
        markup.add(types.InlineKeyboardButton(f"{option_text}", callback_data=f"toggle_{idx}"))

    markup.add(types.InlineKeyboardButton("Submit", callback_data="submit_checklist"))
    restart_button = types.InlineKeyboardButton("Restart", callback_data="restart")
    markup.add(restart_button)
    return markup


def checklist(message, checklist_options):
    """Send checklist to the user with toggle options."""
    try:
        numbered_list = "\n".join([f"{idx + 1}. {option}" for idx, option in enumerate(checklist_options)])
        full_message = f"Please select the options by checking or unchecking:\n\n{numbered_list}"

        bot.send_message(
            message.chat.id,
            full_message,
            reply_markup=create_checklist_markup(message.from_user.id, checklist_options)
        )
    except Exception as e:
        logger.error(f"Error in sending checklist: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def toggle_checklist(call):
    """Toggle the checked/unchecked state of an option."""
    try:
        user_id = call.from_user.id
        option_idx = int(call.data.split("_")[1])
        user_data = ast.literal_eval(r.get(user_id).decode("utf-8"))
        age_group = user_data['age_group']

        user_data['checklist'][option_idx] = not user_data['checklist'][option_idx]
        r.set(user_id, str(user_data))

        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_checklist_markup(user_id, checklist_options[age_group])
        )

    except Exception as e:
        logger.error(f"Error toggling checklist: {e}")


@bot.callback_query_handler(func=lambda call: call.data == "submit_checklist")
def submit_checklist(call):
    """Handle checklist submission."""
    try:
        user_id = call.from_user.id
        user_data = ast.literal_eval(r.get(str(user_id)).decode("utf-8"))

        bot.send_message(call.message.chat.id, "Calculating development age...")
        dev_age = get_dev_age_from_gpt(str(user_data['checklist']), user_data['age_group'])
        bot.send_message(call.message.chat.id, f"Estimated development age is: {dev_age}")
        
        user_data['dev_age'] = dev_age
        word_dev_age = get_word_age(dev_age)
        user_data['word_dev_age'] = word_dev_age
        # print(user_data['age_group'], user_data['dev_age'])
        delay = ((user_data['age_group'] - user_data['dev_age']) * 100) / user_data['age_group']

        if delay < 0:
            delay = 0

        r.set(user_id, str(user_data))

        bot.send_message(call.message.chat.id, f"The child is estimated to be functioning in the {word_dev_age} age range.")
        bot.send_message(call.message.chat.id, f"There is a {delay}% delay in the child's development.")
        bot.send_message(call.message.chat.id, f"Proceeding with recommendations")
        
        recommendations = generate_recommendations(str(user_data['checklist']), user_data['age_group'])
        user_data['recommendations'] = recommendations
        r.set(user_id, str(user_data))

        bot.send_message(call.message.chat.id, f"Based on the assessment, here are the recommendations for the child:")
        bot.send_message(call.message.chat.id, recommendations, parse_mode="Markdown")

        markup = types.InlineKeyboardMarkup()
        yes_button = types.InlineKeyboardButton("Yes", callback_data="generate_report")
        no_button = types.InlineKeyboardButton("No", callback_data="restart")
        markup.add(yes_button, no_button)
        bot.send_message(call.message.chat.id, "Would you like to generate a report?", reply_markup=markup)

    except Exception as e:
        logger.error(f"Error submitting checklist: {e}")
        bot.send_message(call.message.chat.id, "An error occurred while submitting the checklist. Please try again later.")


def format_years_months(months):
    years = months // 12
    remaining_months = months % 12
    
    result = f"{years} years, {remaining_months} months" if years else f"{remaining_months} months"
    
    return result


@bot.callback_query_handler(func=lambda call: call.data == "generate_report")
def generate_report(call):
    """Generate the report and display email options."""
    try:
        user_id = call.from_user.id
        user_data = ast.literal_eval(r.get(str(user_id)).decode("utf-8"))

        default_subject = f"Milestones Report - {user_data['name']} - {datetime.now().strftime('%d/%m/%y %H:%M')}"
        default_body = f"""
Hello,
            
Here are the development assessment results for {user_data['name']},  This child is currently {format_years_months(user_data['age'])} months old and is performing in the {user_data['word_dev_age']} range according to ASHA Developmental Milestones. The recommendations for the team and family are to:
        
{user_data['recommendations']}
        
For exact age equivalencies a formal full speech and language assessment is needed. See this https://www.asha.org/public/developmental-milestones/communication-milestones/ from ASHA for further recommendations.

Best Regards,
Milestones Bot
    """

        user_data['email_subject'] = default_subject
        user_data['email_body'] = default_body
        r.set(user_id, str(user_data))

        bot.send_message(call.message.chat.id, f"Subject: {default_subject}")
        bot.send_message(call.message.chat.id, f"Body:\n{default_body}")

        markup = types.InlineKeyboardMarkup()
        subject_button = types.InlineKeyboardButton("Change Subject", callback_data="change_subject")
        body_button = types.InlineKeyboardButton("Change Body", callback_data="change_body")
        send_button = types.InlineKeyboardButton("Send Email", callback_data="send_email")
        markup.add(subject_button, body_button, send_button)

        bot.send_message(call.message.chat.id, "You can change the subject or body, or send the email.", reply_markup=markup)

    except Exception as e:
        logger.error(f"Error generating report: {e}")
        bot.send_message(call.message.chat.id, "An error occurred while generating the report. Please try again.")


@bot.callback_query_handler(func=lambda call: call.data == "change_subject")
def change_subject(call):
    """Prompt the user to enter a new subject."""
    try:
        msg = bot.send_message(call.message.chat.id, "Please enter a new subject:")
        bot.register_next_step_handler(msg, set_new_subject)

    except Exception as e:
        logger.error(f"Error changing subject: {e}")


def set_new_subject(message):
    """Update the subject with user input."""
    try:
        user_id = message.from_user.id
        new_subject = message.text

        user_data = ast.literal_eval(r.get(str(user_id)).decode("utf-8"))
        user_data['email_subject'] = new_subject
        r.set(user_id, str(user_data))

        bot.send_message(message.chat.id, f"Subject updated to: {new_subject}")

    except Exception as e:
        logger.error(f"Error setting new subject: {e}")


@bot.callback_query_handler(func=lambda call: call.data == "change_body")
def change_body(call):
    """Prompt the user to enter a new body."""
    try:
        msg = bot.send_message(call.message.chat.id, "Please enter a new body for the email:")
        bot.register_next_step_handler(msg, set_new_body)

    except Exception as e:
        logger.error(f"Error changing body: {e}")


def set_new_body(message):
    """Update the body with user input."""
    try:
        user_id = message.from_user.id
        new_body = message.text

        user_data = ast.literal_eval(r.get(str(user_id)).decode("utf-8"))
        user_data['email_body'] = new_body
        r.set(user_id, str(user_data))

        bot.send_message(message.chat.id, "Email body updated successfully.")

    except Exception as e:
        logger.error(f"Error setting new body: {e}")


@bot.callback_query_handler(func=lambda call: call.data == "send_email")
def send_email_action(call):
    """Send the email using the stored subject and body."""
    try:
        user_id = call.from_user.id
        user_data = ast.literal_eval(r.get(str(user_id)).decode("utf-8"))

        subject = user_data['email_subject']
        body = user_data['email_body']

        for to_email in TO_EMAIL:
            send_email(subject, body, to_email)

        bot.send_message(call.message.chat.id, "Email sent successfully!")

    except Exception as e:
        logger.error(f"Error sending email: {e}")
        bot.send_message(call.message.chat.id, "An error occurred while sending the email. Please try again later.")


def age_more_than_range(message):
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
        # bot.send_message(message.chat.id, f"Child's name and age saved: {user_data}", parse_mode="Markdown")

        if age <= 3:
            age_group = 3
        elif age <= 6:
            age_group = 6
        elif age <= 9:
            age_group = 9
        elif age <= 12:
            age_group = 12
        elif age <= 18:
            age_group = 18
        elif age <= 24:
            age_group = 24
        elif age <= 36:
            age_group = 36
        elif age <= 48:
            age_group = 48 
        else:
            age_group = 60  

        user_data = ast.literal_eval(r.get(message.from_user.id).decode("utf-8"))
        user_data["age_group"] = age_group
        r.set(message.from_user.id, str(user_data))    

        checklist(message, checklist_options[age_group])
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
