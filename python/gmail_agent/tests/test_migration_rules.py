from __future__ import annotations

import unittest

from gmail_agent.migration import infer_target_from_message, plan_message_reclassification


class MigrationRuleTests(unittest.TestCase):
    def test_indeed_job_overrides_wrong_financial_label(self) -> None:
        message = {
            "id": "m1",
            "threadId": "t1",
            "from": "Indeed <alert@indeed.com>",
            "subject": "Brivia esta contratando para Atendimento Publicitario",
            "snippet": "Oportunidades para voce nas empresas",
            "body_text": "Candidate-se para vagas nas empresas",
            "labelIds": ["finance_debt"],
        }
        label_lookup = {"finance_debt": "02_FINANCEIRO/EM_ATRASO"}

        plan = plan_message_reclassification(message, label_lookup)

        self.assertEqual(plan["target_label"], "01_PROFI/VAGAS")
        self.assertIn("02_FINANCEIRO/EM_ATRASO", plan["remove_labels"])

    def test_commercial_promotion_uses_publicidade_promocoes(self) -> None:
        message = {
            "from": "Banco <ofertas@example.com>",
            "subject": "Aproveite seu cartao sem anuidade",
            "snippet": "Cashback e limite especial por tempo limitado",
            "body_text": "Oferta exclusiva com vantagens comerciais para voce.",
        }

        self.assertEqual(infer_target_from_message(message, []), "07_PUBLICIDADE-PROMOCOES")

    def test_old_profissional_label_maps_to_new_profi_label(self) -> None:
        message = {
            "id": "m2",
            "threadId": "t2",
            "from": "Jobs <jobs@example.com>",
            "subject": "Nova vaga",
            "snippet": "Oportunidade aberta",
            "labelIds": ["old_jobs"],
        }
        label_lookup = {"old_jobs": "01_PROFISSIONAL/VAGAS"}

        plan = plan_message_reclassification(message, label_lookup)

        self.assertEqual(plan["target_label"], "01_PROFI/VAGAS")
        self.assertIn("01_PROFISSIONAL/VAGAS", plan["remove_labels"])


if __name__ == "__main__":
    unittest.main()
