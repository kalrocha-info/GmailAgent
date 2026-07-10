import unittest

from gmail_agent.filters import build_filter_specs
from gmail_agent.migration import (
    ARCHIVE_TARGET_LABELS,
    archive_stale_inbox_messages,
    infer_target_from_message,
)


class _ModifyRecorder:
    def __init__(self) -> None:
        self.calls = []

    def users(self):
        return self

    def messages(self):
        return self

    def modify(self, **kwargs):
        self.calls.append(kwargs)
        return self

    def execute(self):
        return {}


class ArchivePolicyTests(unittest.TestCase):
    def test_overdue_financial_messages_are_archive_targets(self) -> None:
        self.assertIn("02_FINANCEIRO/EM_ATRASO", ARCHIVE_TARGET_LABELS)

    def test_overdue_financial_filters_skip_the_inbox(self) -> None:
        overdue_actions = [
            actions
            for _, actions in build_filter_specs()
            if actions.get("label") == "02_FINANCEIRO/EM_ATRASO"
        ]

        self.assertTrue(overdue_actions)
        self.assertTrue(all(actions.get("shouldArchive") == "true" for actions in overdue_actions))

    def test_stale_urgent_message_stays_in_inbox(self) -> None:
        gmail = _ModifyRecorder()
        report = {
            "labels": [
                {"id": "INBOX", "name": "INBOX"},
                {"id": "urgent", "name": "03_URGENTE"},
            ],
            "messages": [
                {"id": "m1", "subject": "Ação necessária", "labelIds": ["INBOX", "urgent"]},
            ],
        }

        result = archive_stale_inbox_messages(gmail, report, limit=10)

        self.assertEqual(result["summary"]["messages_archived"], 0)
        self.assertEqual(gmail.calls, [])
        self.assertEqual(result["skipped"][0]["reason"], "categoria deve permanecer na caixa de entrada")

    def test_stale_archive_category_is_removed_from_inbox(self) -> None:
        gmail = _ModifyRecorder()
        report = {
            "labels": [
                {"id": "INBOX", "name": "INBOX"},
                {"id": "newsletter", "name": "06_NEWSLETTER"},
            ],
            "messages": [
                {"id": "m2", "subject": "Newsletter", "labelIds": ["INBOX", "newsletter"]},
            ],
        }

        result = archive_stale_inbox_messages(gmail, report, limit=10)

        self.assertEqual(result["summary"]["messages_archived"], 1)
        self.assertEqual(gmail.calls[0]["body"]["removeLabelIds"], ["INBOX"])

    def test_unknown_message_is_left_for_review(self) -> None:
        message = {
            "from": "Pessoa <pessoa@example.com>",
            "subject": "Olá",
            "snippet": "Podemos conversar amanhã?",
            "body_text": "Sem sinais classificáveis.",
        }

        self.assertIsNone(infer_target_from_message(message, []))


if __name__ == "__main__":
    unittest.main()
