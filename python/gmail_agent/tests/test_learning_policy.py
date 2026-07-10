import unittest

from gmail_agent.learning import rebuild_learning_state


def _message(message_id: str, sender: str, label_id: str) -> dict:
    return {"id": message_id, "from": sender, "labelIds": [label_id]}


class LearningPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.labels = [
            {"id": "manual_finance", "name": "AGENTE/FINANCEIRO/CONTAS"},
            {"id": "manual_jobs", "name": "AGENTE/TRABALHO/VAGAS"},
        ]

    def test_single_manual_example_does_not_create_sender_rule(self) -> None:
        report = {
            "labels": self.labels,
            "messages": [_message("1", "Banco <contato@banco.test>", "manual_finance")],
        }

        state = rebuild_learning_state(report)

        self.assertEqual(state["sender_rules"], {})

    def test_consistent_examples_create_rule_with_confidence(self) -> None:
        report = {
            "labels": self.labels,
            "messages": [
                _message("1", "Banco <contato@banco.test>", "manual_finance"),
                _message("2", "Banco <contato@banco.test>", "manual_finance"),
            ],
        }

        state = rebuild_learning_state(report)

        rule = state["sender_rules"]["contato@banco.test"]
        self.assertEqual(rule["target_label"], "02_FINANCEIRO/CONTAS")
        self.assertEqual(rule["confidence"], 1.0)

    def test_inconsistent_sender_does_not_create_rule(self) -> None:
        report = {
            "labels": self.labels,
            "messages": [
                _message("1", "Contato <multi@example.test>", "manual_finance"),
                _message("2", "Contato <multi@example.test>", "manual_finance"),
                _message("3", "Contato <multi@example.test>", "manual_jobs"),
            ],
        }

        state = rebuild_learning_state(report)

        self.assertNotIn("multi@example.test", state["sender_rules"])


if __name__ == "__main__":
    unittest.main()
