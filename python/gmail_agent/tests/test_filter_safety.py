import unittest

from gmail_agent.filters import apply_filters
from gmail_agent.migration import TARGET_LABELS


class _Request:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class _LabelsApi:
    def __init__(self, labels) -> None:
        self._labels = labels

    def list(self, **_kwargs):
        return _Request({"labels": self._labels})


class _FiltersApi:
    def __init__(self, fail_on_create=None) -> None:
        self.fail_on_create = fail_on_create
        self.create_count = 0
        self.deleted = []
        self.existing = [{"id": "old-filter", "criteria": {"from": "old@example.com"}}]

    def list(self, **_kwargs):
        return _Request({"filter": self.existing})

    def create(self, **_kwargs):
        self.create_count += 1
        if self.create_count == self.fail_on_create:
            return _Request(error=RuntimeError("falha simulada"))
        return _Request({"id": f"new-{self.create_count}"})

    def delete(self, **kwargs):
        self.deleted.append(kwargs["id"])
        return _Request({})


class _SettingsApi:
    def __init__(self, filters_api) -> None:
        self._filters_api = filters_api

    def filters(self):
        return self._filters_api


class _UsersApi:
    def __init__(self, labels_api, filters_api) -> None:
        self._labels_api = labels_api
        self._settings_api = _SettingsApi(filters_api)

    def labels(self):
        return self._labels_api

    def settings(self):
        return self._settings_api


class _Gmail:
    def __init__(self, labels, fail_on_create=None) -> None:
        self.filters_api = _FiltersApi(fail_on_create=fail_on_create)
        self._users_api = _UsersApi(_LabelsApi(labels), self.filters_api)

    def users(self):
        return self._users_api


class FilterSafetyTests(unittest.TestCase):
    def test_missing_label_aborts_before_reading_or_deleting_filters(self) -> None:
        gmail = _Gmail(labels=[])

        result = apply_filters(gmail, replace_existing=True)

        self.assertEqual(result["summary"]["created"], 0)
        self.assertEqual(gmail.filters_api.create_count, 0)
        self.assertEqual(gmail.filters_api.deleted, [])

    def test_creation_failure_rolls_back_new_filters_and_preserves_old(self) -> None:
        labels = [{"id": f"label-{index}", "name": name} for index, name in enumerate(TARGET_LABELS)]
        gmail = _Gmail(labels=labels, fail_on_create=2)

        result = apply_filters(gmail, replace_existing=True)

        self.assertGreater(result["summary"]["failed"], 0)
        self.assertIn("new-1", gmail.filters_api.deleted)
        self.assertNotIn("old-filter", gmail.filters_api.deleted)
        self.assertEqual(result["existing_backup"], gmail.filters_api.existing)


if __name__ == "__main__":
    unittest.main()
