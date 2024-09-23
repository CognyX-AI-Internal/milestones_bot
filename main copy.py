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
import re

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
r = Redis(connection_pool=pool)

AGE_GROUPS = [3, 6, 9, 12, 18, 24, 36, 48, 60]

with open("checklist_options.json", "r", encoding="utf-8") as f:
    checklist_options = ast.literal_eval(f.read())
checklist_options = {int(k): v for k, v in checklist_options.items()}

with open("suggestions.json", "r", encoding="utf-8") as f:
    suggestions = ast.literal_eval(f.read())
suggestions = {int(k): v for k, v in suggestions.items()}

def escape_markdown_v2(text):
    """Escape characters for Telegram MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)


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
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You have to strictly respond with a number referring to the age in months."
                        "Do not add any other text to the response."
                        "If the unit is not strictly mentioned, it is referring to years and convert it to months."
                        "If it is not possible to extract the age, return 'None'."
                    ),
                },
                {
                    "role": "user",
                    "content": message
                },
            ],
            temperature=0.7,
        )
        report = response.choices[0].message.content.strip()
        return int(report)
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

        system_content = (
            f"You have to strictly respond with a number referring to the age in months.\n"
            f"Do not add any other text to the response.\n"
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
        report = response.choices[0].message.content.strip()
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
            "You will receive a list of tuples, where the True/False value indicates whether the child has hit a milestone or not."
            "Return a list of recommendations so that the user can improve."
            "Do not return recommendations where the user has already hit a milestone."
            f"Strictly stick to the following recommendations {str(suggestions[age_group])}."
            "The recommendations should be in Markdown format."
        )

        response = openai_client.chat.completions.create(            model="gpt-4",
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
        report = response.choices[0].message.content.strip()
        return report
    except Exception as e:
        logger.error(f"Error generating recommendations from chatGPT: {e}")
        return None

def generate_recommendations_new(message,age):
    try:
        openai_client = openai.OpenAI(
                    api_key=os.environ.get("OPENAI_API_KEY"),
                )
       
        system_content = (
            "1. BASE INSTRUCTIONS:\n"
            "You are the world's leading expert on ASHA communication development milestones screening.\n"
            "You will receive:\n"
            "- The child's chronological age.\n"
            "- A list of communication milestones met by the child.\n"

            "Using this information, you will generate a comprehensive report titled **`SPEECH AND LANGUAGE THERAPY REPORT`** following the specified format. The report should include:\n"
            "- **Overview** section (static text provided below).\n"
            "- **Observations** section (dynamic based on the child's age and milestones).\n"
            "- **Milestones Achieved** section (based on the developmental age range).\n"
            "- **Milestones Expected but Not Met** section (only include unmet milestones from the current developmental age range).\n"         
            "- **Recommendations for Parents** (only addressing areas of need).\n"
            "- **Recommendations for the Clinical Team** (only addressing areas of need).\n"

            "**Important:**\n"
            "- Do **not** include recommendations for milestones the child has already met.\n"
            "- If the child meets all milestones for their current developmental age range, omit the ** Milestones Expected but Not Met ** section or state that all milestones are met.\n"
            "- Ensure all recommendations are relevant to the areas of need identified.\n"
            
            "\n\n2. ASHA Communication development milestones (FOR YOUR CONTEXT):\n"

            "[Birth to 3 Months:]\n"
            "Alerts to sound.\n"
            "Quiets or smiles when you talk.\n"
            "Makes sounds back and forth with you.\n"
            "Makes sounds that differ depending on whether they are happy or upset.\n"
            "Coos, makes sounds like ooooo, aahh, and mmmmm.\n"
            "Recognizes loved ones and some common objects.\n"
            "Turns or looks toward voices or people talking.\n\n"

            "[4 to 6 Months:]\n"
            "Giggles and laughs.\n"
            "Responds to facial expressions.\n"
            "Looks at objects of interest and follows objects with their eyes.\n"
            "Reacts to toys that make sounds, like those with bells or music.\n"
            "Vocalizes during play or with objects in mouth.\n"
            "Vocalizes different vowel sounds—sometimes combined with a consonant—like uuuuuummm, aaaaaaagoo, or daaaaaaaaaa.\n"
            "Blows “raspberries.”\n\n"

            "[7 to 9 Months:]\n"
            "Looks at you when you call their name.\n"
            "Stops for a moment when you say, “No.”\n"
            "Babbles long strings of sounds, like mamamama, upup, or babababa.\n"
            "Looks for loved ones when upset.\n"
            "Raises arms to be picked up.\n"
            "Recognizes the names of some people and objects.\n"
            "Pushes away unwanted objects.\n\n"

            "[10 to 12 Months:]\n"
            "By age 10 months, reaches for objects.\n"
            "Points, waves, and shows or gives objects.\n"
            "Imitates and initiates gestures for engaging in social interactions and playing games, like blowing kisses or playing peek-a-boo.\n"
            "Tries to copy sounds that you make.\n"
            "Enjoys dancing.\n"
            "Responds to simple words and phrases like “Go bye-bye” and “Look at Mommy.”\n"
            "Says one or two words—like mama, dada, hi, and bye.\n\n"

            "[13 to 18 months:]\n"
            "Looks around when asked “where” questions—like “Where’s your blanket?”\n"
            "Follows directions—like “Give me the ball,” “Hug the teddy bear,” “Come here,” or “Show me your nose.”\n"
            "Points to make requests, to comment, or to get information.\n"
            "Shakes head for “no” and nods head for “yes.”\n"
            "Understands and uses words for common objects, some actions, and people in their lives.\n"
            "Identifies one or more body parts.\n"
            "Uses gestures when excited, like clapping or giving a high-five, or when being silly, like sticking out their tongue or making funny faces.\n"
            "Uses a combination of long strings of sounds, syllables, and real words with speech-like inflection.\n\n"

            "[19 to 24 months:]\n"
            "Uses and understands at least 50 different words for food, toys, animals, and body parts. Speech may not always be clear—like du for “shoe” or dah for “dog.”\n"
            "Puts two or more words together—like more water or go outside.\n"
            "Follows two-step directions—like “Get the spoon, and put it on the table.”\n"
            "Uses words like me, mine, and you.\n"
            "Uses words to ask for help.\n"
            "Uses possessives, like Daddy’s sock.\n\n"

            "[2 to 3 years:]\n"
            "Uses word combinations often but may occasionally repeat some words or phrases, like baby – baby – baby sit down or I want – I want juice.\n"
            "Tries to get your attention by saying, Look at me!\n"
            "Says their name when asked.\n"
            "Uses some plural words like birds or toys.\n"
            "Uses –ing verbs like eating or running. Adds –ed to the end of words to talk about past actions, like looked or played.\n"
            "Gives reasons for things and events, like saying that they need a coat when it’s cold outside.\n"
            "Asks why and how.\n"
            "Answers questions like “What do you do when you are sleepy?” or “Which one can you wear?”\n"
            "Correctly produces p, b, m, h, w, d, and n in words.\n"
            "Correctly produces most vowels in words.\n"
            "Speech is becoming clearer but may not be understandable to unfamiliar listeners or to people who do not know your child.\n\n"

            "[3 to 4 years:]\n"
            "Compares things, with words like bigger or shorter.\n"
            "Tells you a story from a book or a video.\n"
            "Understands and uses more location words, like inside, on, and under.\n"
            "Uses words like a or the when talking, like a book or the dog.\n"
            "Pretends to read alone or with others.\n"
            "Recognizes signs and logos like STOP.\n"
            "Pretends to write or spell and can write some letters.\n"
            "Correctly produces t, k, g, f, y, and –ing in words.\n"
            "Says all the syllables in a word.\n"
            "Says the sounds at the beginning, middle, and end of words.\n"
            "By age 4 years, your child talks smoothly. Does not repeat sounds, words, or phrases most of the time.\n"
            "By age 4 years, your child speaks so that people can understand most of what they say. Child may make mistakes on sounds that are later to develop—like l, j, r, sh, ch, s, v, z, and th.\n"
            "By age 4 years, your child says all sounds in a consonant cluster containing two or more consonants in a row—like the tw in tweet or the –nd in sand. May not produce all sounds correctly—for example, spway for “spray.\n\n"

            "[4 to 5 years:]\n"
            "Produces grammatically correct sentences. Sentences are longer and more complex.\n"
            "Includes (1) main characters, settings, and words like and to connect information and (2) ideas to tell stories.\n"
            "Uses at least one irregular plural form, like feet or men.\n"
            "Understands and uses location words, like behind, beside, and between.\n"
            "Uses more words for time—like yesterday and tomorrow—correctly.\n"
            "Follows simple directions and rules to play games.\n"
            "Locates the front of a book and its title.\n"
            "Recognizes and names 10 or more letters and can usually write their own name.\n"
            "Imitates reading and writing from left to right.\n"
            "Blends word parts, like cup + cake = cupcake. Identifies some rhyming words, like cat and hat.\n"
            "Produces most consonants correctly, and speech is understandable in conversation.\n\n\n"
            
            "3. OUTPUT INSTRUCTIONS:\n"
            "Use the provided information about the child to fill in the dynamic sections.\n\n"
            
            "**Follow these instructions for the output:**\n"
            "- **Format:** Ensure the report follows the exact Markdown format, including headings and bullet points.\n"
            "- **Developmental Age Range:** Determine the highest ASHA developmental age range for which the child has met all required milestones.\n"
            "- **Milestones Achieved:** List only the milestones achieved within the determined developmental age range.\n"
            "- **Milestones Expected but Not Met:** Include only the unmet milestones from the current developmental age range. Do **not** include milestones from higher age ranges.\n"
            "- **Delay Percentage:** Calculate and include the delay percentage only if there are unmet milestones.\n"
            "- **Recommendations:** Provide recommendations solely based on the unmet milestones.\n"

            "## SPEECH AND LANGUAGE THERAPY REPORT\n"

            "## Child's Age:\n"
            "[Insert Child’s Age Here]"

            "## Overview:\n"
            "The Communication Milestone Screening Protocol: Birth to 5 (CMSP: B-5) was given based on parent report and/or clinical observation.\n\n"
            "The CMSP: B-5 is a criterion-based speech and language screening tool for children from birth to age 5. It incorporates parent reports, observations in natural environments, and session documentation, systematically comparing findings to the ASHA Developmental Milestones for speech and language. This tool is designed to identify early signs of potential communication delays and to inform decisions regarding the need for further comprehensive assessment.\n\n"

            "## Observations:\n"
            "[Child’s Name] is [Child’s Current Age] old at the time of screening. Based on the ASHA Developmental Milestones, the child’s speech and language abilities are functioning at the developmental range of [Developmental Age Range] according to their milestones. Clinical observations and parent reports indicate the following:\n"
            "- [Bullet Point 1]\n"
            "- [Bullet Point 2]\n"
            "- [Bullet Point 3]\n"

            "These observations indicate a potential delay in expressive and receptive language development compared to the expected developmental milestones for a child of [Child’s Name]’s age.\n"

            "## Milestones Achieved:\n"

            "## Milestones Achieved:\n"
            "At the [Developmental Age Range] developmental level, [Child’s Name] has demonstrated the following abilities:\n"
            "- **Expressive Language:**\n"
            "- [Bullet Point 1]\n"
            "- [Bullet Point 2]\n"
            "- **Receptive Language:**\n"
            "- [Bullet Point]\n"
            "- **Social Communication:**\n"
            "- [Bullet Point]\n"
            "- [Bullet Point]\n"

            "## Milestones Expected but Not Met (Based on [Child’s Current Age] ASHA Developmental Milestones):\n"
            "- **Expressive Language:**\n"
            "- [Bullet Point]\n"
            "- [Bullet Point]\n"
            "- [Bullet Point]\n"
            "- **Receptive Language:**\n"
            "- [Bullet Point]\n"
            "- [Bullet Point]\n"
            "- [Bullet Point]\n"

            "The child presents with a delay of approximately [Minimum Percentage]% to [Maximum Percentage]% in communication development based on their chronological age of [Child’s Age] and their estimated developmental age range of [Developmental Age Range].\n"


            "   ### Recommendations for Parents:\n"
            "1. **Speech and Language Enrichment:**\n"
            "- [Sub Bullet]\n"
            "- [Sub Bullet]\n"
            "- [Sub Bullet]\n"
            "- [Sub Bullet]\n"
            "- [Sub Bullet]\n"
            "3. **Books and Songs:**\n"
            "- [Sub Bullet]\n"
            "- [Sub Bullet]\n"

            "### Recommendations for the Clinical Team:\n"
            "1. **Further Evaluation:**\n"
            "- [Sub Bullet]\n"
            "2. **Early Intervention Services:**\n"
            "- [Sub Bullet]\n"
            "- [Sub Bullet]\n"
            "3. **Ongoing Monitoring:**\n"
            "- [Sub Bullet]\n"

            
            # "\n\nFollow the below Markdown Format for your response:\n"
            # "##SPEECH AND LANGUAGE THERAPY REPORT\n"
            # "Child's Age: "
            # "\n##Overview:(Keep the following as it is.)\n"
            # "The Communication Milestone Screening Protocol: Birth to 5 (CMSP: B-5) was given based on parent report and/or clinical observation.\n\n"
            # "The CMSP: B-5 is a criterion-based speech and language screening tool for children from birth to age 5. It incorporates parent reports, observations in natural environments, and session documentation, systematically comparing findings to the ASHA Developmental Milestones for speech and language. This tool is designed to identify early signs of potential communication delays and to inform decisions regarding the need for further comprehensive assessment.\n\n"
            # "##Observations:(Mention the child's current age, State the developmental age range of the child according to ASHA milestones based on their milestones, Add clinical observations and parent reports with bullet points, Include a concluding statement summarizing the observations.)\n\n"
            # "##Milestones Achieved: (List the milestones achieved according to the developmental age range you concluded. Categorize them by Expressive Language,Receptive Language, Social Communication or any other categories of ASHA with bullets and sub-bullets)\n\n"
            # "##Milestones Expected but Not Met (Based on [child's current age range] ASHA Developmental Milestones): (Include only the ASHA milestones of his current biological age range not met by the child (Keep blank if all milestones of the current age range are met), categorize accordingly with bullets and sub-bullets. Add this line in the end Strictly ONLY if child is not meeting the milestones of his age range: `The child presents with a delay of approximately [Minimum Percentage]% to [Maximum Percentage]% in communication development based on their chronological age of [Child’s Age] and their estimated developmental age range of [Developmental Age Range].`')\n\n"
            # "##Recommendations for Parents: (Numbered points with sub bullet points of recommendations to parents.)\n\n"
            # "##Recommendations for the Clinical Team: (Numbered points with sub bullet points of recommendations to the clinical team.)\n\n"
        )


        response = openai_client.chat.completions.create(            model="gpt-4o-2024-08-06",
            messages=[
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": "Current age of the child: "+ str(age) +", Milestones met by child: "+message
                },
            ],
            temperature=0.7,
        )
        report = response.choices[0].message.content.strip()
        print(report)
        return report
    except Exception as e:
        logger.error(f"Error generating recommendations from chatGPT: {e}")
        return None

def get_word_age(dev_age):
    try:
        openai_client = openai.OpenAI(
                    api_key=os.environ.get("OPENAI_API_KEY"),
                )        
        response = openai_client.chat.completions.create(            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You have to strictly respond with age."
                        "Do not add any other text to the response."
                        "You will receive an age in months; you have to reply in this format: years, months."
                        "Ignore the years part if the input is less than 12."
                        "For example, 15: 1 year, 3 months."
                    ),
                },
                {
                    "role": "user",
                    "content": str(dev_age)
                },
            ],
            temperature=0.7,
        )
        report = response.choices[0].message.content.strip()
        return report
    except Exception as e:
        logger.error(f"Error generating word age from chatGPT: {e}")
        return None    


def create_checklist_markup(user_id, checklist_options):
    """Create a checklist markup with current selections and additional options."""
    user_data = ast.literal_eval(r.get(user_id).decode("utf-8"))
    
    age_group = user_data['age_group']
    if 'checklists' not in user_data:
        user_data['checklists'] = {age_group: [False] * len(checklist_options)}
        r.set(user_id, str(user_data))

    checklist = user_data['checklists'].get(age_group, [False] * len(checklist_options))

    markup = types.InlineKeyboardMarkup()
    for idx, option in enumerate(checklist_options):
        status = "✅" if checklist[idx] else "⬜️"
        option_text = f"{status} {option}".ljust(73, ' ')
        markup.add(types.InlineKeyboardButton(f"{option_text}", callback_data=f"toggle_{idx}"))

    # Add "See Previous Milestones" button if not at the youngest age group
    if age_group != AGE_GROUPS[0]:
        prev_button = types.InlineKeyboardButton("See Previous Milestones", callback_data="previous_milestones")
        markup.add(prev_button)

    markup.add(types.InlineKeyboardButton("Submit", callback_data="submit_checklist"))
    restart_button = types.InlineKeyboardButton("Restart", callback_data="restart")
    markup.add(restart_button)
    return markup

def checklist(message, checklist_options):
    """Send checklist to the user with toggle options."""
    try:
        numbered_list = "\n".join([f"{idx + 1}. {option}" for idx, option in enumerate(checklist_options)])
        full_message = f"Please select the milestones achieved:\n\n{numbered_list}"
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

        if 'checklists' not in user_data:
            user_data['checklists'] = {}

        if age_group not in user_data['checklists']:
            user_data['checklists'][age_group] = [False] * len(checklist_options[age_group])

        checklist = user_data['checklists'][age_group]
        checklist[option_idx] = not checklist[option_idx]
        user_data['checklists'][age_group] = checklist
        r.set(user_id, str(user_data))

        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_checklist_markup(user_id, checklist_options[age_group])
        )

    except Exception as e:
        logger.error(f"Error toggling checklist: {e}")


@bot.callback_query_handler(func=lambda call: call.data == "previous_milestones")
def show_previous_milestones(call):
    """Display the previous age group's milestones."""
    try:
        user_id = call.from_user.id
        user_data = ast.literal_eval(r.get(user_id).decode("utf-8"))
        current_age_group = user_data['age_group']
        current_index = AGE_GROUPS.index(current_age_group)

        if current_index > 0:
            previous_age_group = AGE_GROUPS[current_index - 1]
            user_data['age_group'] = previous_age_group
            if previous_age_group not in user_data['checklists']:
                user_data['checklists'][previous_age_group] = [False] * len(checklist_options[previous_age_group])
            r.set(user_id, str(user_data))
            numbered_list = "\n".join([f"{idx + 1}. {option}" for idx, option in enumerate(checklist_options[previous_age_group])])
            full_message = f"Showing milestones for {previous_age_group} months:\n\n{numbered_list}"
            
            bot.send_message(
                call.message.chat.id,
                full_message,
                reply_markup=create_checklist_markup(user_id, checklist_options[previous_age_group])
            )
        else:
            bot.send_message(call.message.chat.id, "No previous milestones available.")

    except Exception as e:
        logger.error(f"Error showing previous milestones: {e}")

# ... existing code ...

@bot.callback_query_handler(func=lambda call: call.data == "submit_checklist")
def submit_checklist(call):
    """Handle checklist submission."""
    try:
        user_id = call.from_user.id
        user_data = ast.literal_eval(r.get(user_id).decode("utf-8"))

        # Collect milestones from all age groups
        achieved_milestones = []
        for age_group, checklist in user_data['checklists'].items():
            for idx, achieved in enumerate(checklist):
                if achieved:
                    achieved_milestones.append(checklist_options[age_group][idx])

        # Format the checklist for user-friendly display
        formatted_checklist = "\n".join([f"{idx + 1}. {milestone}" for idx, milestone in enumerate(achieved_milestones)])

        # Proceed with calculating development age and recommendations
        bot.send_message(call.message.chat.id, 'Milestones achieved by the child:\n' + formatted_checklist)
        # bot.send_message(call.message.chat.id, "Calculating development age...")
        # dev_age = get_dev_age_from_gpt(str(user_data['checklists'][user_data['age_group']]), user_data['age_group'])
        # bot.send_message(call.message.chat.id, f"Estimated development age is: {dev_age}")

        # user_data['dev_age'] = dev_age
        # word_dev_age = get_word_age(dev_age)
        # user_data['word_dev_age'] = word_dev_age
        # delay = ((user_data['age_group'] - dev_age) * 100) / user_data['age_group']
        # delay = max(delay, 0)
        # r.set(user_id, str(user_data))

        # bot.send_message(call.message.chat.id, f"The child is estimated to be functioning in the {word_dev_age} age range.")
        # bot.send_message(call.message.chat.id, f"There is a {delay}% delay in the child's development.")
        # bot.send_message(call.message.chat.id, "Proceeding with recommendations...")

        recommendations = generate_recommendations_new(formatted_checklist, user_data["age"])
        escaped_recommendations = escape_markdown_v2(recommendations)

        user_data['recommendations'] = recommendations
        r.set(user_id, str(user_data))

        bot.send_message(call.message.chat.id, "Based on the screening, here are the recommendations for the child:")
        bot.send_message(call.message.chat.id, escaped_recommendations, parse_mode="MarkdownV2")

        # Ask if user wants to generate a report
        markup = types.InlineKeyboardMarkup()
        yes_button = types.InlineKeyboardButton("Yes", callback_data="generate_report")
        no_button = types.InlineKeyboardButton("No", callback_data="restart")
        markup.add(yes_button, no_button)
        bot.send_message(call.message.chat.id, "Would you like to generate a report?", reply_markup=markup)

    except Exception as e:
        logger.error(f"Error submitting checklist: {e}")
        bot.send_message(call.message.chat.id, "An error occurred while submitting the checklist. Please try again later.")

# ... existing code ...
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
            
Here are the development screening results for {user_data['name']},  This child is currently {format_years_months(user_data['age'])} months old and is performing in the {user_data['word_dev_age']} range according to ASHA Developmental Milestones. The recommendations for the team and family are to:
        
{user_data['recommendations']}
        
For exact age equivalencies a formal full speech and language screening is needed. See this https://www.asha.org/public/developmental-milestones/communication-milestones/ from ASHA for further recommendations.

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

        restart_button = types.InlineKeyboardButton("Restart", callback_data="restart")
        markup.add(restart_button)

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
        markup = types.InlineKeyboardMarkup()
        subject_button = types.InlineKeyboardButton("Change Subject", callback_data="change_subject")
        body_button = types.InlineKeyboardButton("Change Body", callback_data="change_body")
        send_button = types.InlineKeyboardButton("Send Email", callback_data="send_email")
        markup.add(subject_button, body_button, send_button)
        bot.send_message(message.chat.id, "You can now change the subject or body, or send the email.", reply_markup=markup)

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
        markup = types.InlineKeyboardMarkup()
        subject_button = types.InlineKeyboardButton("Change Subject", callback_data="change_subject")
        body_button = types.InlineKeyboardButton("Change Body", callback_data="change_body")
        send_button = types.InlineKeyboardButton("Send Email", callback_data="send_email")
        markup.add(subject_button, body_button, send_button)
        bot.send_message(message.chat.id, "You can now change the subject or body, or send the email.", reply_markup=markup)

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
        
        markup = types.InlineKeyboardMarkup()
        restart_button = types.InlineKeyboardButton("Restart", callback_data="restart")
        markup.add(restart_button)

        bot.send_message(call.message.chat.id, "Would you like to restart?", reply_markup=markup)

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