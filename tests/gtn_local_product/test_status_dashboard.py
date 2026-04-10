from __future__ import annotations

import unittest

from runtime.gtn_local_product.status_dashboard import latest_version_display


class StatusDashboardVersionTests(unittest.TestCase):
    def test_latest_version_display_marks_update_available_only_when_pypi_is_newer(self) -> None:
        self.assertEqual(
            latest_version_display('0.2.1', 'installed', '0.2.2', None),
            '0.2.2 (update available)',
        )
        self.assertEqual(
            latest_version_display('0.2.10', 'installed', '0.2.2', None),
            '0.2.2 (local build ahead)',
        )

    def test_latest_version_display_marks_failed_checks(self) -> None:
        self.assertEqual(
            latest_version_display('0.2.1', 'installed', None, 'ssl failed'),
            '(check failed)',
        )
