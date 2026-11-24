"""Telegram entry point for the D&D dice bot."""

from collections import deque
from dataclasses import dataclass, field
import logging
from pathlib import Path
from threading import Lock
from time import monotonic

import telebot
from telebot.apihelper import ApiException
from telebot.types import Message

from dice_parser import DICE_SIDES, MAX_EXPRESSION_LENGTH
from service import find_formulas, roll_replies
from telegram_replies import ReplySender


TOKEN_PATH = Path("token.txt")
MAX_FORMULA_FILE_BYTES = 4 * MAX_EXPRESSION_LENGTH
REQUESTS_PER_WINDOW = 5
RATE_WINDOW_SECONDS = 10
RATE_LIMIT_MESSAGE = "Слишком много запросов. Попробуй чуть позже."
HELP = (
    "Пиши формулы прямо в сообщении. Например, <code>Бросок d20</code>.\n\n"
    "<b>Кубики</b>\n"
    f"{', '.join(f'<code>d{sides}</code>' for sides in DICE_SIDES)}\n"
    "<code>d20</code> или <code>d20()</code> — один бросок.\n"
    "<code>3d6</code>, <code>3d6()</code> или <code>d6(3)</code> — сумма трёх бросков.\n"
    "<code>2к20</code> или <code>2к20()</code> — запись с кириллической <code>к</code>.\n\n"
    "<b>Формулы</b>\n"
    "<code>3d6+5</code> — модификатор. <code>(2d6()+5)*2</code> — скобки.\n"
    "Операции <code>+ - * / // **</code>. <code>//</code> округляет вниз, <code>**</code> возводит в степень. "
    "В десятичных числах используй точку, например <code>d20+1.5</code>.\n\n"
    "<b>Выбор кубиков</b>\n"
    "<code>d20kh</code> — преимущество, <code>d20kl</code> — помеха. Оба варианта бросают два d20 и оставляют один.\n"
    "<code>d20kh+5</code> = <code>2d20kh1+5</code>. <code>d20kl+5</code> = <code>2d20kl1+5</code>.\n"
    "<code>4d6kh3</code> оставит три наибольших, <code>4d6kl2</code> — два наименьших.\n"
    "🎲 отмечает обычный бросок. 🔥 и 💀 отмечают натуральные 20 и 1 среди оставленных d20. "
    "Отброшенные кубики зачёркнуты, итог выделен жирным.\n\n"
    "<b>Несколько бросков и подписи</b>\n"
    "<code>d20; 2d6+3</code> — два отдельных броска. Можно писать их на разных строках, "
    "в том числе в нумерованном списке.\n"
    "<code>2d6 — Урон мечом</code> — подпись после тире с пробелами до конца строки.\n\n"
    f"Формулы до {MAX_EXPRESSION_LENGTH} символов можно прислать файлом <code>.txt</code> в UTF-8. "
    "Длинный результат придёт файлом.\n\n"
    "<code>/start</code> — приветствие. <code>/help</code> — эта справка."
)


@dataclass
class UserRequests:
    accepted: deque[float] = field(default_factory=deque)
    last_notice: float = float("-inf")


class RateLimiter:
    def __init__(self):
        self.users: dict[int, UserRequests] = {}
        self.next_cleanup = 0.0
        self.lock = Lock()

    def check(self, user_id: int) -> tuple[bool, bool]:
        """Return whether to allow the request and whether to notify about rejection."""
        with self.lock:
            now = monotonic()
            cutoff = now - RATE_WINDOW_SECONDS
            if now >= self.next_cleanup:
                self.users = {
                    user: requests
                    for user, requests in self.users.items()
                    if requests.accepted[-1] > cutoff or requests.last_notice > cutoff
                }
                self.next_cleanup = now + RATE_WINDOW_SECONDS

            requests = self.users.setdefault(user_id, UserRequests())
            while requests.accepted and requests.accepted[0] <= cutoff:
                requests.accepted.popleft()
            if len(requests.accepted) < REQUESTS_PER_WINDOW:
                requests.accepted.append(now)
                return True, False
            if requests.last_notice <= cutoff:
                requests.last_notice = now
                return False, True
            return False, False


def read_token(path: Path) -> str:
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise SystemExit(f"Не удалось прочитать токен из {path}.") from None
    if not token:
        raise SystemExit(f"Файл {path} пуст.")
    number, separator, secret = token.partition(":")
    valid_id = number.isascii() and number.isdecimal()
    valid_secret = secret and secret.isascii() and all(char.isalnum() or char in "_-" for char in secret)
    if not (separator and valid_id and valid_secret):
        raise SystemExit(f"Неверный формат токена в {path}.")
    return token


def create_bot(token: str, *, threaded: bool = True) -> telebot.TeleBot:
    bot = telebot.TeleBot(token, threaded=threaded)
    limiter = RateLimiter()
    sender = ReplySender(bot, threaded=threaded)

    def allow_request(message: Message) -> bool:
        if message.sender_chat is not None:
            user_id = message.sender_chat.id
        else:
            user_id = message.from_user.id if message.from_user is not None else message.chat.id
        allowed, notify = limiter.check(user_id)
        if notify:
            sender.submit(message, (RATE_LIMIT_MESSAGE,))
        return allowed

    @bot.message_handler(commands=["start", "help"])
    def send_help(message: Message) -> None:
        command, separator, recipient = message.text.split(maxsplit=1)[0][1:].partition("@")
        if separator and (not recipient or recipient.casefold() != (bot.user.username or "").casefold()):
            return
        if allow_request(message):
            sender.submit(message, (HELP if command == "help" else "Привет ✌️ ",))

    @bot.message_handler(content_types=["text"])
    def roll(message: Message) -> None:
        formulas = find_formulas(message.text)
        if formulas and allow_request(message):
            sender.submit(message, roll_replies(formulas))

    @bot.message_handler(
        content_types=["document"],
        func=lambda message: (message.document.file_name or "").lower().endswith(".txt"),
    )
    def roll_file(message: Message) -> None:
        if not allow_request(message):
            return
        document = message.document
        oversized = f"Файл должен занимать не больше {MAX_FORMULA_FILE_BYTES} байт."
        if document.file_size is not None and document.file_size > MAX_FORMULA_FILE_BYTES:
            sender.submit(message, (oversized,))
            return
        try:
            file = bot.get_file(document.file_id)
            size = file.file_size if file.file_size is not None else document.file_size
            if size is None or not file.file_path:
                sender.submit(message, ("Не удалось получить файл.",))
                return
            if size > MAX_FORMULA_FILE_BYTES:
                sender.submit(message, (oversized,))
                return
            content = bot.download_file(file.file_path)
        except (ApiException, OSError):
            sender.submit(message, ("Не удалось скачать файл.",))
            return
        if len(content) > MAX_FORMULA_FILE_BYTES:
            sender.submit(message, (oversized,))
            return
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            sender.submit(message, ("Сохрани .txt в кодировке UTF-8.",))
            return
        formulas = find_formulas(text)
        replies = roll_replies(formulas) if formulas else ["В файле нет формул с кубиками."]
        sender.submit(message, replies)

    return bot


def main() -> None:
    bot = create_bot(read_token(TOKEN_PATH))
    telebot.logger.setLevel(logging.INFO)
    bot.infinity_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
