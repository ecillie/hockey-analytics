#!/usr/bin/env python3

import unittest

from latest_release_branch import latest_release_branch


class LatestReleaseBranchTests(unittest.TestCase):
    def test_compares_each_numeric_component_from_left_to_right(self) -> None:
        branches = [
            "Release-2.99.99",
            "Release-10.0.0",
            "Release-10.1.8",
            "Release-10.1.12",
        ]

        self.assertEqual(latest_release_branch(branches), "Release-10.1.12")

    def test_ignores_non_release_and_inexact_branch_names(self) -> None:
        branches = [
            "Dev",
            "ReleaseCandidate",
            "Release-MVP",
            "Release-1.2",
            "release-9.9.9",
            "Release-1.2.3-hotfix",
            "Release-1.2.3",
        ]

        self.assertEqual(latest_release_branch(branches), "Release-1.2.3")

    def test_fails_when_no_release_branch_exists(self) -> None:
        with self.assertRaisesRegex(ValueError, "No Release-MAJOR.MINOR.PATCH"):
            latest_release_branch(["Dev", "Prod", "Release-MVP"])


if __name__ == "__main__":
    unittest.main()
