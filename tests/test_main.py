from pathlib import Path
import logging
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from telebot.types import Message

import main


class TelegramTests(unittest.TestCase):
    def setUp(self):
        pacing = patch("telegram_replies.GROUP_INTERVAL", 0)
        pacing.start()
        self.addCleanup(pacing.stop)
        self.bot = main.create_bot("123456:test_only", threaded=False)
        self.message_id = 0

    def receive(self, text=None, *, user_id=1, topic=None, document=None):
        self.message_id += 1
        payload = {
            "message_id": self.message_id,
            "from": {"id": user_id, "is_bot": False, "first_name": "Тест"},
            "chat": {"id": -100, "type": "supergroup"},
            "date": 1,
        }
        if document is None:
            payload["text"] = text
        else:
            payload["document"] = {"file_id": "test", "file_unique_id": "test", "file_name": "roll.txt", **document}
        if topic is not None:
            payload.update(message_thread_id=topic, is_topic_message=True)
        self.bot.process_new_messages([Message.de_json(payload)])

    def test_start_help_and_roll_reply_to_original_with_html(self):
        with patch.object(self.bot, "send_message") as send, patch("service.random.randint", return_value=20):
            self.receive("обычный текст")
            self.receive("/start")
            self.receive("/help")
            self.receive("Бросок d20 — Атака <мечом>", topic=4)
        self.assertEqual(send.call_count, 3)
        for original_id, call in enumerate(send.call_args_list, 2):
            self.assertEqual(call.args[0], -100)
            self.assertEqual(call.kwargs["reply_parameters"].message_id, original_id)
            self.assertEqual(call.kwargs["parse_mode"], "HTML")
        self.assertIn("Привет", send.call_args_list[0].args[1])
        help_text = send.call_args_list[1].args[1]
        for example in (
            "d100", "d6(3)", "2к20()", "(2d6()+5)*2", "+ - * / // **",
            "d20kl", "d20kh", "2d20kl1+5", "4d6kh3", "d20; 2d6+3", "2d6 — Урон мечом",
        ):
            with self.subTest(help_example=example):
                self.assertIn(example, help_text)
        self.assertEqual(send.call_args.args[1], "🔥20 = <b>20</b> — Атака &lt;мечом&gt;")
        self.assertEqual(send.call_args.kwargs["message_thread_id"], 4)

    def test_short_disadvantage_and_invalid_keep_rule(self):
        with patch.object(self.bot, "send_message") as send, patch("service.random.randint", side_effect=[1, 20]) as roll:
            self.receive("\u200e\u2068d20kl\u2069")
            self.receive("d20khl")
        self.assertEqual(roll.call_count, 2)
        self.assertEqual(send.call_args_list[0].args[1], "[💀1, <s>🎲20</s>] = <b>1</b>")
        self.assertIn("Для преимущества — d20kh, для помехи — d20kl.", send.call_args.args[1])

    def test_every_chunk_and_error_replies_to_the_original_message(self):
        with patch.object(self.bot, "send_message") as send, patch("service.random.randint", return_value=6):
            self.receive("+".join(["100d6kh1"] * 5))
            self.assertGreater(send.call_count, 1)
            self.assertTrue(all(call.kwargs["reply_parameters"].message_id == 1 for call in send.call_args_list))
            self.receive("d6()+")
        self.assertEqual(send.call_args.kwargs["reply_parameters"].message_id, 2)
        self.assertEqual(send.call_args.args[1], "Неверная формула.")

    def test_reads_long_txt_and_replies_with_the_complete_result_file(self):
        repeats = (main.MAX_EXPRESSION_LENGTH - 2) // 2
        text = "d6" + "+1" * repeats
        downloaded = text.encode("utf-8")
        file = SimpleNamespace(file_size=len(downloaded), file_path="documents/file.txt")
        files = []

        def record_file(chat_id, document, **kwargs):
            self.assertEqual(chat_id, -100)
            self.assertEqual(kwargs["reply_parameters"].message_id, 1)
            self.assertEqual(kwargs["message_thread_id"], 4)
            files.append(document.file.read().decode("utf-8"))

        with (
            patch.object(self.bot, "get_file", return_value=file) as get_file,
            patch.object(self.bot, "download_file", return_value=downloaded) as download,
            patch.object(self.bot, "send_document", side_effect=record_file) as send_document,
            patch.object(self.bot, "send_message") as send,
            patch("service.random.randint", return_value=2),
        ):
            self.receive(document={"file_size": len(downloaded)}, topic=4)
        get_file.assert_called_once_with("test")
        download.assert_called_once_with(file.file_path)
        send_document.assert_called_once()
        send.assert_not_called()
        self.assertIn(f"🎲2{' + 1' * repeats} = <b>{2 + repeats}</b>", files[0])

    def test_txt_errors_are_reported_as_replies(self):
        file = SimpleNamespace(file_size=3, file_path="documents/file.txt")
        with (
            patch.object(self.bot, "get_file", return_value=file) as get_file,
            patch.object(self.bot, "download_file", return_value=b"\xff\xfe\x00") as download,
            patch.object(self.bot, "send_message") as send,
        ):
            self.receive(document={"file_size": main.MAX_FORMULA_FILE_BYTES + 1})
            get_file.assert_not_called()
            self.receive(document={"file_size": 3})
            download.assert_called_once()
        self.assertIn("не больше", send.call_args_list[0].args[1])
        self.assertIn("UTF-8", send.call_args_list[1].args[1])

    def test_addressed_commands_are_checked_before_rate_limiting(self):
        identity = SimpleNamespace(username="Dice_Bot")
        with patch.object(self.bot, "get_me", return_value=identity) as get_me, patch.object(self.bot, "send_message") as send:
            for _ in range(main.REQUESTS_PER_WINDOW + 1):
                self.receive("/help@another_bot")
            self.receive("/start@another_bot")
            self.assertEqual(send.call_count, 0)
            self.receive("/help@dICE_bOT")
            self.receive("/start@Dice_Bot")
        get_me.assert_called_once()
        self.assertEqual([call.args[1] for call in send.call_args_list], [main.HELP, "Привет ✌️ "])

    def test_rate_limiting_and_expiration(self):
        with patch.object(self.bot, "send_message") as send, patch("service.random.randint", return_value=4) as roll:
            with patch("main.monotonic", return_value=100):
                for _ in range(main.REQUESTS_PER_WINDOW + 3):
                    self.receive("d6")
                self.assertEqual(roll.call_count, main.REQUESTS_PER_WINDOW)
                self.assertEqual(send.call_count, main.REQUESTS_PER_WINDOW + 1)
                self.assertEqual(send.call_args.args[1], main.RATE_LIMIT_MESSAGE)
                self.assertEqual(send.call_args.kwargs["reply_parameters"].message_id, main.REQUESTS_PER_WINDOW + 1)
                self.receive("d6", user_id=2)
            with patch("main.monotonic", return_value=100 + main.RATE_WINDOW_SECONDS):
                self.receive("d6")
            self.assertEqual(roll.call_count, main.REQUESTS_PER_WINDOW + 2)
            self.assertEqual(send.call_args.args[1], "🎲4 = <b>4</b>")

    def test_reads_token_and_starts_polling(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "token.txt"
            path.write_text("  123456:test_only\n", encoding="utf-8")
            with (
                patch.object(main, "TOKEN_PATH", path),
                patch.object(main.telebot.logger, "setLevel") as set_level,
                patch.object(main.telebot.TeleBot, "infinity_polling") as poll,
            ):
                main.main()
            set_level.assert_called_once_with(logging.INFO)
            poll.assert_called_once_with(allowed_updates=["message"])

    def test_token_errors_do_not_report_the_secret(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "token.txt"
            with self.assertRaisesRegex(SystemExit, "Не удалось прочитать"):
                main.read_token(path)
            path.write_text(" \n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "пуст"):
                main.read_token(path)
            path.write_text("private bad token", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "Неверный формат") as caught:
                main.read_token(path)
            self.assertNotIn("private bad token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
