from zoneinfo import ZoneInfo
import telebot
from telebot.types import Message, User, Chat
from os import getenv
from dotenv import load_dotenv
from telebot.types import ReplyKeyboardMarkup, ReplyKeyboardRemove
import logging
import json
from dataclasses import asdict, dataclass, field
from typing import List
from datetime import datetime


# =====================================
# initialize
# =====================================

load_dotenv(".CRMEnv")
bot_token = getenv("TOKEN")
print("Using token ...", bot_token[-3:])


class Settings:

    def _load_setting(name, mandatory=True):
        value = getenv(name)
        if mandatory and not value:
            raise ValueError(f"Setting '{name}' is missing!")
        return value

    LOG_FILE = _load_setting("log_file", False)
    LOG_LEVEL = _load_setting("log_level", False)
    LOG_TO_CONSOLE = _load_setting("log_level", False)

    admin_users = _load_setting("admin_users", False)
    ADMIN_USERS = admin_users.lower().split() if admin_users else []

    CHATS_FILE = _load_setting("chats_file", False) or "crmchats.json"


if Settings.LOG_FILE:
    handlers = [logging.FileHandler(Settings.LOG_FILE, encoding="utf-8")]
    if Settings.LOG_TO_CONSOLE:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=Settings.LOG_LEVEL or logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


logger = logging.getLogger()


class ChatStates:
    NEW = "new"
    Q1 = "q1"
    Q2 = "q2"
    EXTRA = "extra"


tz = ZoneInfo("Europe/Moscow")


def get_ts():
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class UserAnswer:
    qid: str
    answer: str
    timestamp: str = field(default_factory=get_ts)

    @staticmethod
    def from_dict(data: dict) -> "UserAnswer":
        return UserAnswer(**data)


@dataclass
class ChatState:
    cid: int
    current: str
    uname: str
    tgid: str
    answers: List[UserAnswer] = field(default_factory=list)

    def to_dict(self):
        return {
            "cid": self.cid,
            "current": self.current,
            "uname": self.uname,
            "tgid": self.tgid,
            "answers": [asdict(ans) for ans in self.answers],
        }

    @staticmethod
    def from_dict(data: dict):
        answers = [UserAnswer.from_dict(a) for a in data.get("answers", [])]
        return ChatState(
            cid=data["cid"],
            current=data["current"],
            uname=data["uname"],
            tgid=data["tgid"],
            answers=answers,
        )


bot = telebot.TeleBot(bot_token)


message: Message = None
known_chats = {}
chat_state = None


def save_data():
    try:
        states = [state.to_dict() for state in known_chats.values()]
        with open(Settings.CHATS_FILE, "w", encoding="UTF-8") as json_file:
            json.dump(states, json_file, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(states)} chats to {Settings.CHATS_FILE}")
    except Exception as ex:
        logger.error("Failed to save chats", exc_info=ex)


def load_data():
    try:
        with open(Settings.CHATS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        for d in data:
            state = ChatState.from_dict(d)
            known_chats[state.cid] = state
        logger.info(f"Loaded {len(data)} chats from {Settings.CHATS_FILE}")
    except Exception as ex:
        logger.error("Failed to load chats", exc_info=ex)


load_data()


# =====================================
# bot functions
# =====================================


def log_message():
    pretty_json = json.dumps(message.json, indent=4)
    logger.debug(
        f"""
Message received: {type(message)} {message.content_type}
    User id:    {message.from_user.id}  {message.from_user.username}
    Chat:       {message.chat.id}  {message.chat.type}
    Text:       {message.text}
    JSON:       
{pretty_json}
"""
    )
    print(f"Сообщение от {message.from_user.username}:\n{message.text}")


def get_chat_state(msg: Message):
    global chat_state
    global message
    message = msg
    log_message()
    cid = message.chat.id
    if cid in known_chats.keys():
        logger.debug(f"Reusing chat state {cid}")
        chat_state = known_chats[cid]
    else:
        logger.debug(f"Adding chat state {cid}")
        uname = (
            message.from_user.full_name
            if message.from_user.full_name
            else message.from_user.username
        )
        chat_state = ChatState(
            cid=cid,
            current=ChatStates.NEW,
            uname=uname,
            tgid=message.from_user.username,
        )
        known_chats[cid] = chat_state
    logger.debug(chat_state)
    return chat_state.current


def send_greeting():
    text = f"""Привет {chat_state.uname}! 👋 

Спасибо за интерес к теме ERP и CRM.

Чтобы получить максимальную пользу от мероприятия, просим ответить на пару простых вопросов. Это займет всего минуту!

Готовы? Тогда начнём.
"""
    bot.send_message(message.chat.id, text)


def send_q1():
    text = f"""1. К какой категории вы бы себя отнесли?
Нажмите кнопку с вариантом ответа внизу, либо напишите свой вариант.
"""
    keyboard = ReplyKeyboardMarkup(row_width=1)
    button1 = telebot.types.KeyboardButton("Предприниматель")
    button2 = telebot.types.KeyboardButton("Наёмный руководитель")
    button3 = telebot.types.KeyboardButton("Специалист IT")
    button4 = telebot.types.KeyboardButton("Специалист, не IT")
    keyboard.add(button1, button2, button3, button4)

    bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)

    chat_state.current = ChatStates.Q1


def start_admin():
    text = f"Для вас доступна функция статистики /stat"
    bot.send_message(chat_id=message.chat.id, text=text)


def start_new_chat():
    send_greeting()
    send_q1()


def send_q2():
    text = f"""2. Собираетесь ли вы внедрять новые ERP/CRM системы на вашем предприятии в ближайшее время?
"""
    keyboard = ReplyKeyboardMarkup(row_width=2)
    button1 = telebot.types.KeyboardButton("Да")
    button2 = telebot.types.KeyboardButton("Нет")
    keyboard.add(button1, button2)

    bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)

    chat_state.current = ChatStates.Q2


def send_finish():
    text = f"""Благодарим вас за участие!
    
    Если у вас есть вопросы или вы хотите сообщить дополнительную информацию организаторам, - можете написать в этом чате.
"""
    bot.send_message(
        chat_id=message.chat.id, text=text, reply_markup=ReplyKeyboardRemove()
    )
    chat_state.current = ChatStates.EXTRA


def reply_extra():
    text = f"""Ваше сообщение будет передано организаторам.
"""
    bot.send_message(
        chat_id=message.chat.id, text=text, reply_markup=ReplyKeyboardRemove()
    )
    chat_state.current = ChatStates.EXTRA


def send_stat():
    text = f"""
Зарегистрировано {len(known_chats)} участников.
"""


# =====================================
# handlers and polling
# =====================================


@bot.message_handler()
def handle_message(message: Message):
    if get_chat_state(message) == ChatStates.NEW or message.text.lower() == "/start":
        start_new_chat()
        if isAdmin():
            start_admin()
    else:
        if isAdmin() and message.text.lower() == "/stat":
            display_stat()
        else:
            save_answer()
            match chat_state.current:
                case ChatStates.Q1:
                    send_q2()
                case ChatStates.Q2:
                    send_finish()
                case ChatStates.EXTRA:
                    reply_extra()
                case _:
                    # state not catched elsewhere
                    # handle it by starting over
                    start_new_chat()


def isAdmin():
    return message.from_user.username.lower() in Settings.ADMIN_USERS


def print_info(message):
    info = f"""Вы написали: `{message.text}`
Пользователь: `{message.from_user.username}`
Чат: `{message.chat.id}`
"""
    print(info)
    bot.send_message(message.chat.id, info, parse_mode="Markdown")


def display_stat():
    stat = "\n\n".join(map(get_stat, list(known_chats.values())[-8:]))
    info = f"""Статистика регистраций:\n\n{stat}"""
    print(info)
    bot.send_message(message.chat.id, info)


def get_stat(cs: ChatState):
    parts = ['@' + cs.tgid]
    if cs.uname != cs.tgid:
        parts.append(cs.uname)
    q1 = q2 = extra = ts = ""
    for a in cs.answers:
        if a.qid == "q1":
            q1 = a.answer
        if a.qid == "q2":
            q2 = a.answer
        if a.qid == "extra":
            extra = a.answer
        ts = a.timestamp
    parts.append("Q1: " + q1)
    parts.append("Q2: " + q2)
    if extra:
        parts.append(extra)
    if ts:
        parts.append(ts[:-3])
    return "\n".join(parts)


def save_answer():
    chat_state.answers.append(UserAnswer(chat_state.current, message.text))


bot.infinity_polling()


save_data()
