from html.parser import HTMLParser
from itertools import product
import unittest

from dice_parser import DICE_SIDES, MAX_DICE_PER_EXPRESSION, MAX_EXPRESSION_LENGTH, MAX_FORMULAS
from service import MAX_DESCRIPTION_LENGTH, MAX_REPLY_LENGTH, RollDocument, find_formulas, roll_replies


def replies(text, *values):
    faces = iter(values)

    def randint(low, high):
        value = next(faces)
        if not low <= value <= high:
            raise AssertionError(f"Test die result {value} outside {low}–{high}")
        return value

    result = roll_replies(find_formulas(text), randint=randint)
    if next(faces, None) is not None:
        raise AssertionError("Some expected dice were not rolled")
    return result


class DiceServiceTests(unittest.TestCase):
    def test_examples(self):
        cases = [
            ("d20()", (12,), "🎲12 = <b>12</b>"),
            ("d20", (5,), "🎲5 = <b>5</b>"),
            ("3d6()", (4, 2, 6), "🎲4 + 🎲2 + 🎲6 = <b>12</b>"),
            ("3d6", (4, 2, 6), "🎲4 + 🎲2 + 🎲6 = <b>12</b>"),
            ("2к20", (14, 11), "🎲14 + 🎲11 = <b>25</b>"),
            ("2к20()", (14, 11), "🎲14 + 🎲11 = <b>25</b>"),
            ("d20()+5", (15,), "🎲15 + 5 = <b>20</b>"),
            ("2d20()+5", (14, 11), "🎲14 + 🎲11 + 5 = <b>30</b>"),
            ("2d20()+5", (20, 11), "🔥20 + 🎲11 + 5 = <b>36</b>"),
            ("2d20()+5", (1, 11), "💀1 + 🎲11 + 5 = <b>17</b>"),
            ("2d20()+5", (20, 1), "🔥20 + 💀1 + 5 = <b>26</b>"),
            ("3d6()+5", (4, 2, 6), "🎲4 + 🎲2 + 🎲6 + 5 = <b>17</b>"),
            ("2d20()+3d6()+5", (14, 11, 4, 2, 6), "🎲14 + 🎲11 + 🎲4 + 🎲2 + 🎲6 + 5 = <b>42</b>"),
            ("(2d6()+5)*2", (4, 6), "(🎲4 + 🎲6 + 5) × 2 = <b>30</b>"),
            ("2d20kh1+5", (7, 20), "[<s>🎲7</s>, 🔥20] + 5 = <b>25</b>"),
            ("2d20kl1+5", (1, 20), "[💀1, <s>🎲20</s>] + 5 = <b>6</b>"),
            ("4d6kh3", (1, 6, 4, 3), "[<s>🎲1</s>, 🎲6, 🎲4, 🎲3] = <b>13</b>"),
            ("4d6kl2", (5, 2, 4, 1), "[<s>🎲5</s>, 🎲2, <s>🎲4</s>, 🎲1] = <b>3</b>"),
        ]
        for text, faces, expected in cases:
            with self.subTest(text=text, faces=faces):
                self.assertEqual(replies(text, *faces), [expected])

    def test_all_dice_and_legacy_count(self):
        self.assertEqual(
            replies("d4+d6+d8+d10+d12+d20+d100", 4, 1, 8, 10, 12, 2, 20),
            ["🎲4 + 🎲1 + 🎲8 + 🎲10 + 🎲12 + 🎲2 + 🎲20 = <b>57</b>"],
        )
        self.assertEqual(replies("d6(2+1)", 2, 1, 3), ["🎲2 + 🎲1 + 🎲3 = <b>6</b>"])
        self.assertEqual(replies("0d6()"), ["0 = <b>0</b>"])

    def test_marks_only_kept_critical_dice_and_breaks_ties_in_roll_order(self):
        self.assertEqual(replies("2d20kh1", 1, 20), ["[<s>🎲1</s>, 🔥20] = <b>20</b>"])
        self.assertEqual(replies("2d20()kh1", 20, 20), ["[🔥20, <s>🎲20</s>] = <b>20</b>"])

    def test_keep_shorthand_defaults_and_explicit_counts(self):
        self.assertEqual(replies("d20kl", 20, 1), replies("2d20kl1", 20, 1))
        self.assertEqual(replies("d20kh+5", 7, 20), replies("2d20kh1+5", 7, 20))
        self.assertEqual(replies("4d6kl", 5, 3, 4, 2), replies("4d6kl1", 5, 3, 4, 2))
        self.assertEqual(replies("к20()kh", 7, 20), replies("2d20kh1", 7, 20))
        self.assertEqual(replies("d20(3)kl", 14, 2, 8), replies("3d20kl1", 14, 2, 8))
        self.assertEqual(replies("d20kl1", 7), ["[🎲7] = <b>7</b>"])
        self.assertEqual(replies("1d20kh", 7), ["[🎲7] = <b>7</b>"])

    def test_keep_shorthand_across_dice_notations(self):
        notations = ("{}{}", "{}(){}", "{}{}()")
        rules = ("kh", "kl", "KH", "KL")
        for sides, letter, notation, rule in product(DICE_SIDES, "dDкК", notations, rules):
            text = notation.format(f"{letter}{sides}", rule)
            canonical = f"2d{sides}{rule.lower()}1"
            for faces in ((1, sides), (sides, 1), (sides, sides), (2, 3)):
                with self.subTest(text=text, faces=faces):
                    self.assertEqual(replies(text, *faces), replies(canonical, *faces))

    def test_keep_shorthand_across_explicit_roll_counts(self):
        for sides, rule, count in product(DICE_SIDES, ("kh", "kl"), (1, 2, 4, 100)):
            faces = tuple(index % sides + 1 for index in range(count))
            canonical = f"{count}d{sides}{rule}1"
            for text in (f"{count}d{sides}{rule}", f"d{sides}({count}){rule}"):
                with self.subTest(text=text):
                    self.assertEqual(replies(text, *faces), replies(canonical, *faces))

    def test_invalid_keep_rules_for_every_die(self):
        suffixes = ("k", "khl", "klh", "kh0", "kl0", "kh2", "kl2", "kh1kl1", "kl1x")
        for sides, suffix in product(DICE_SIDES, suffixes):
            text = f"d{sides}{suffix}"
            with self.subTest(text=text):
                result = replies(text)
                self.assertEqual(len(result), 1)
                self.assertNotIn("<b>", result[0])

    def test_precedence_with_dice_expansion(self):
        cases = [
            ("2d6*d4", (4, 6, 2), "(🎲4 + 🎲6) × 🎲2 = <b>20</b>"),
            ("20-2d6", (4, 6), "20 - (🎲4 + 🎲6) = <b>10</b>"),
            ("d20/(2*(2d6-1))", (16, 2, 3), "🎲16 / (2 × (🎲2 + 🎲3 - 1)) = <b>2.0</b>"),
            ("d6//3+9/2", (4,), "🎲4 // 3 + 9 / 2 = <b>5.5</b>"),
            ("-2d6**2", (1, 2), "-(🎲1 + 🎲2) ^ 2 = <b>-9</b>"),
            ("(-d6)**2", (3,), "(-🎲3) ^ 2 = <b>9</b>"),
            ("d6+2**3**2", (4,), "🎲4 + 2 ^ 3 ^ 2 = <b>516</b>"),
            ("2**-d6", (2,), "2 ^ (-🎲2) = <b>0.25</b>"),
        ]
        for text, faces, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(replies(text, *faces), [expected])

    def test_text_extraction_and_multiple_formulas(self):
        self.assertEqual(replies("Я принёс обычный текст и abcD20."), [])
        self.assertEqual(
            replies("Бросок d20() (атака), потом (проверка d4). И (d8+1)*2!", 18, 3, 2),
            ["🎲18 = <b>18</b>\n🎲3 = <b>3</b>\n(🎲2 + 1) × 2 = <b>6</b>"],
        )

    def test_numbered_lines_and_decimal_literals(self):
        self.assertEqual(
            replies("1. d20+5\n  2) d6\n3. + d4\n1.5 + d8", 14, 3, 2, 4),
            ["🎲14 + 5 = <b>19</b>\n🎲3 = <b>3</b>\n3.0 + 🎲2 = <b>5.0</b>\n1.5 + 🎲4 = <b>5.5</b>"],
        )

    def test_unsupported_internal_punctuation_does_not_truncate_a_roll(self):
        for text in ("d20!+5", "d20!!+5", "d20 ! + 5", "2! + d6", "d6·2"):
            with self.subTest(text=text):
                self.assertEqual(replies(text), ["Неверная формула."])
        self.assertEqual(replies("Бросок d6! Затем d8?", 3, 8), ["🎲3 = <b>3</b>\n🎲8 = <b>8</b>"])

    def test_optional_descriptions(self):
        self.assertEqual(
            replies("Бросаем — d4; 2d20kh1+5 — Атака <мечом> & d100 — первая\nd6 — Урон", 4, 7, 20, 3),
            ["🎲4 = <b>4</b>\n[<s>🎲7</s>, 🔥20] + 5 = <b>25</b> — Атака &lt;мечом&gt; &amp; d100 — первая\n"
             "🎲3 = <b>3</b> — Урон"],
        )
        caption = "а" * MAX_DESCRIPTION_LENGTH
        self.assertEqual(replies(f"d4 — {caption}", 3), [f"🎲3 = <b>3</b> — {caption}"])
        self.assertIn("длина подписи", replies(f"d4 — {caption}а")[0])

    def test_errors_and_successes_can_share_a_message(self):
        text = "d6()+, d6()d8(), d6()/0, d4"
        self.assertEqual(
            replies(text, 4, 3),
            ["Неверная формула.\nНеверная формула.\nДеление на ноль.\n🎲3 = <b>3</b>"],
        )

    def test_invalid_grammar_is_rejected_before_any_roll(self):
        for text in ("d5", "d6**", "d6kh0", "2d6kl3", "d6k", "d6()xyz", "d6!=5", "d6 % 2",
                     "d6[0]", "d6+word", "d6(", "(d6", "d6)", "2d6(3)", "d6(1.5)", "d6(-1)"):
            with self.subTest(text=text):
                result = replies(text)
                self.assertEqual(len(result), 1)
                self.assertNotIn("<b>", result[0])

    def test_arithmetic_errors(self):
        self.assertEqual(replies("d6+2**101", 2), ["Показатель степени по модулю должен быть не больше 100."])
        self.assertEqual(replies("d6+99**99", 2), ["Слишком большое число."])
        self.assertEqual(replies("d6//0", 1), ["Деление на ноль."])
        self.assertEqual(replies("d6+(-2)**.5", 2), ["Степень даёт комплексное число."])
        self.assertIn(f"<b>{10**100}</b>", replies("0d6+10**100")[0])
        self.assertIn("<b>1e+100</b>", replies("0d6+10.**100")[0])
        self.assertIn("Слишком большое", replies("d6+" + "9" * 102)[0])
        self.assertIn("Слишком большое", replies("d6+" + "9" * (MAX_EXPRESSION_LENGTH - 3))[0])

    def test_limits(self):
        full = "d6" + " " * (MAX_EXPRESSION_LENGTH - 4) + "+1"
        self.assertEqual(replies(full, 2), ["🎲2 + 1 = <b>3</b>"])
        self.assertIn("длина формулы", replies(full.replace("+", " +"))[0])
        self.assertIn(f"{MAX_DICE_PER_EXPRESSION} кубиков", replies(f"{MAX_DICE_PER_EXPRESSION + 1}d6")[0])
        self.assertIn(f"{MAX_DICE_PER_EXPRESSION} кубиков", replies(f"{MAX_DICE_PER_EXPRESSION}d6+d4")[0])
        self.assertEqual(replies(", ".join(["d6"] * (MAX_FORMULAS + 1))), ["Максимум 5 формул в сообщении."])

    def test_very_long_and_deep_expressions(self):
        depth = (MAX_EXPRESSION_LENGTH - 2) // 2
        count_depth = (MAX_EXPRESSION_LENGTH - 5) // 2
        cases = {
            "вложенность": ("(" * depth + "d6" + ")" * depth, 3),
            "сложение": ("d6" + "+1" * depth, 3 + depth),
            "степени": ("1**" * ((MAX_EXPRESSION_LENGTH - 2) // 3) + "d6", 1),
            "унарные знаки": ("-" * (MAX_EXPRESSION_LENGTH - 2) + "d6", 3),
            "старый синтаксис": ("d6(" + "(" * count_depth + "1" + ")" * count_depth + ")", 3),
        }
        for name, (text, expected) in cases.items():
            with self.subTest(expression=name):
                result = replies(text, 3)
                if isinstance(result[0], RollDocument):
                    body = result[0].content.decode("utf-8")
                else:
                    body = "".join(result)
                self.assertIn(f"= <b>{expected}</b>", body)

    def test_large_rolls_keep_every_die_in_chat_or_file(self):
        count = 1_000
        chunks = replies(f"{count}d6", *([1] * count))
        combined = "".join(chunks)
        self.assertEqual(combined.count("🎲1"), count)
        self.assertTrue(combined.endswith(f"= <b>{count}</b>"))

        count = MAX_DICE_PER_EXPRESSION
        document, = replies(f"{count}d6kh1 — <атака>", *([1] * count))
        self.assertIsInstance(document, RollDocument)
        html = document.content.decode("utf-8")
        self.assertEqual(html.count("🎲1"), count)
        self.assertEqual(html.count("<s>"), count - 1)
        self.assertIn("= <b>1</b> — &lt;атака&gt;", html)

    def test_long_replies_keep_all_dice_and_complete_tags(self):
        class TagCheck(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []

            def handle_starttag(self, tag, attrs):
                self.stack.append(tag)

            def handle_endtag(self, tag):
                if self.stack.pop() != tag:
                    raise AssertionError("Unbalanced HTML tags")

        text = "+".join(["100d100kh1"] * 5)
        chunks = replies(text, *([100] * 500))
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.encode("utf-16-le")) // 2, MAX_REPLY_LENGTH)
            parser = TagCheck()
            parser.feed(chunk)
            self.assertEqual(parser.stack, [])
        combined = "".join(chunks)
        self.assertEqual(combined.count("🎲100"), 500)
        self.assertEqual(combined.count("<s>"), 495)
        self.assertTrue(combined.endswith("= <b>500</b>"))


if __name__ == "__main__":
    unittest.main()
