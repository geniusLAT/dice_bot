from threading import Event
import unittest
from unittest.mock import Mock, patch

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import Message

from service import RollDocument
from telegram_replies import BUSY_REPLY, GROUP_INTERVAL, ReplySender


def group_message(chat_id):
    return Message.de_json({
        "message_id": 10,
        "chat": {"id": chat_id, "type": "supergroup"},
        "date": 1,
    })


def flood_error(seconds):
    return ApiTelegramException("sendMessage", Mock(), {
        "error_code": 429,
        "description": "Too Many Requests",
        "parameters": {"retry_after": seconds},
    })


class ReplySenderTests(unittest.TestCase):
    def test_retries_only_the_rejected_chunk_after_telegram_delay(self):
        bot = Mock(spec=TeleBot)
        clock = [0.0]
        attempts = []

        def send(message, text, **kwargs):
            attempts.append((text, clock[0]))
            if len(attempts) == 2:
                raise flood_error(7)

        bot.reply_to.side_effect = send

        def advance(seconds):
            clock[0] += seconds

        with patch("telegram_replies.monotonic", side_effect=lambda: clock[0]), patch("telegram_replies.Condition") as condition:
            condition.return_value.wait.side_effect = advance
            sender = ReplySender(bot, threaded=False)
            message = group_message(-100)
            sender.submit(message, ["первая", "вторая", "третья"])

        self.assertEqual([part for part, _ in attempts], ["первая", "вторая", "вторая", "третья"])
        for first, second, delay in zip(attempts, attempts[1:], (GROUP_INTERVAL, 7, GROUP_INTERVAL)):
            self.assertAlmostEqual(second[1] - first[1], delay)
        for call in bot.reply_to.call_args_list:
            self.assertIs(call.args[0], message)
            self.assertEqual(call.kwargs["parse_mode"], "HTML")

    def test_a_waiting_chat_does_not_block_another_chat(self):
        bot = Mock(spec=TeleBot)
        limited = Event()
        other_sent = Event()
        resumed = Event()
        clock = [0.0]

        def send(message, text, **kwargs):
            if message.chat.id == -200:
                other_sent.set()
            elif limited.is_set():
                resumed.set()
            else:
                limited.set()
                raise flood_error(10)

        bot.reply_to.side_effect = send
        with patch("telegram_replies.monotonic", side_effect=lambda: clock[0]):
            sender = ReplySender(bot, threaded=True)
            sender.submit(group_message(-100), ["бросок в первом чате"])
            try:
                self.assertTrue(limited.wait(2))
                sender.submit(group_message(-200), ["бросок во втором чате"])
                self.assertTrue(other_sent.wait(2))
                self.assertFalse(resumed.is_set())
            finally:
                with sender.condition:
                    clock[0] = 10
                    sender.condition.notify()
                self.assertTrue(resumed.wait(2))

    def test_overflow_replies_with_a_notice_instead_of_sending_a_partial_batch(self):
        bot = Mock(spec=TeleBot)
        message = group_message(-100)
        with patch("telegram_replies.MAX_PENDING_PER_CHAT", 1):
            ReplySender(bot, threaded=False).submit(message, ["первая", "вторая"])
        bot.reply_to.assert_called_once_with(message, BUSY_REPLY, parse_mode="HTML", message_thread_id=None)

    def test_document_bytes_count_until_successful_retry_across_chats(self):
        bot = Mock(spec=TeleBot)
        bot.send_document.side_effect = [flood_error(7), None, None]
        clock = [0.0]
        first = group_message(-100)
        second = group_message(-200)
        document = RollDocument(b"result")

        def advance(seconds):
            sender.submit(second, [document])
            clock[0] += seconds

        with (
            patch("telegram_replies.MAX_PENDING_DOCUMENT_BYTES", len(document.content)),
            patch("telegram_replies.GROUP_INTERVAL", 0),
            patch("telegram_replies.monotonic", side_effect=lambda: clock[0]),
            patch("telegram_replies.Condition") as condition,
        ):
            condition.return_value.wait.side_effect = advance
            sender = ReplySender(bot, threaded=False)
            sender.submit(first, [document])
            sender.submit(second, [document])

        bot.reply_to.assert_called_once_with(second, BUSY_REPLY, parse_mode="HTML", message_thread_id=None)
        self.assertEqual([call.args[0] for call in bot.send_document.call_args_list], [-100, -100, -200])
