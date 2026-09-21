"""Whether a newer release is one worth telling somebody about.

Two things carry the weight here. A version is compared by its numbers alone,
because a build off master carries the released number with its commit after
it and is ahead of that release rather than behind it. And the clock lives in a
file, so a day of asking nobody has to survive a restart.
"""

import json
import time

from dikte import hub
from dikte import update
from tests.support import DikteTest, fake_urlopen, url_error

RELEASE = {
    "tag_name": "v1.4.0",
    "html_url": "https://github.com/yusufipk/dikte/releases/tag/v1.4.0",
    "published_at": "2026-08-01T10:00:00Z",
}


class Numbers(DikteTest):
    def test_a_tag_and_a_bare_number_read_the_same(self):
        self.assertEqual(update._numbers("v1.4.0"), (1, 4, 0))
        self.assertEqual(update._numbers("1.4.0"), (1, 4, 0))

    def test_a_short_number_is_filled_out(self):
        self.assertEqual(update._numbers("2"), (2, 0, 0))
        self.assertEqual(update._numbers("2.1"), (2, 1, 0))

    def test_what_follows_the_number_is_dropped(self):
        self.assertEqual(update._numbers("1.0.1-dev.abc1234"), (1, 0, 1))
        self.assertEqual(update._numbers("1.0.1+build7"), (1, 0, 1))

    def test_something_that_is_not_a_version_is_no_version(self):
        self.assertEqual(update._numbers("latest"), ())
        self.assertEqual(update._numbers(""), ())
        self.assertEqual(update._numbers(None), ())


class Newer(DikteTest):
    def test_a_higher_number_is_newer(self):
        self.assertTrue(update.newer("1.4.0", "1.3.9"))
        self.assertTrue(update.newer("v2.0.0", "1.9.9"))

    def test_the_same_number_is_not(self):
        self.assertFalse(update.newer("1.4.0", "1.4.0"))
        self.assertFalse(update.newer("1.3.0", "1.4.0"))

    def test_a_build_off_master_is_ahead_of_the_release_it_names(self):
        """1.0.1-dev.abc1234 was built after 1.0.1 went out, not before it.
        Read as a version suffix it would be older, and every nightly would be
        told to go back to the release it had already passed."""
        self.assertFalse(update.newer("1.0.1", "1.0.1-dev.abc1234"))
        self.assertTrue(update.newer("1.0.2", "1.0.1-dev.abc1234"))

    def test_a_tag_that_is_not_a_version_is_never_newer(self):
        self.assertFalse(update.newer("nightly", "1.0.0"))


class Asking(DikteTest):
    def setUp(self):
        super().setUp()
        self.patch_attr(hub, "CACHE_DIR", self.path("cache"))
        self.patch_attr(update, "__version__", "1.0.0")

    def test_the_newest_release_comes_back_with_its_page(self):
        with fake_urlopen(RELEASE) as calls:
            release = update.latest()
        self.assertEqual(release.version, "1.4.0")
        self.assertEqual(release.url, RELEASE["html_url"])
        self.assertEqual(
            calls[0].full_url,
            "https://api.github.com/repos/yusufipk/dikte/releases/latest")

    def test_a_release_with_no_page_falls_back_to_the_redirect(self):
        with fake_urlopen({"tag_name": "v1.4.0"}):
            release = update.latest()
        self.assertEqual(release.url, update.RELEASES_PAGE)

    def test_a_repository_with_no_release_is_an_error(self):
        with fake_urlopen({"message": "Not Found"}):
            with self.assertRaises(hub.HubError):
                update.latest()

    def test_a_check_answers_with_the_newer_release(self):
        with fake_urlopen(RELEASE):
            release = update.check()
        self.assertEqual(release.version, "1.4.0")

    def test_a_check_that_finds_nothing_new_answers_with_nothing(self):
        self.patch_attr(update, "__version__", "1.4.0")
        with fake_urlopen(RELEASE):
            self.assertIsNone(update.check())

    def test_a_second_check_the_same_day_asks_nobody(self):
        with fake_urlopen(RELEASE) as calls:
            update.check()
            release = update.check()
        self.assertEqual(len(calls), 1)
        # And still says what the first one found, since it is still true.
        self.assertEqual(release.version, "1.4.0")

    def test_a_day_later_it_asks_again(self):
        with fake_urlopen(RELEASE) as calls:
            update.check()
            update._store(checked=time.time() - update.INTERVAL - 60)
            update.check()
        self.assertEqual(len(calls), 2)

    def test_the_button_asks_whatever_the_clock_says(self):
        with fake_urlopen(RELEASE) as calls:
            update.check()
            update.check(force=True)
        self.assertEqual(len(calls), 2)

    def test_a_check_that_cannot_reach_github_says_so(self):
        with fake_urlopen(url_error("no route to host")):
            with self.assertRaises(hub.HubError):
                update.check()


class Remembering(DikteTest):
    def setUp(self):
        super().setUp()
        self.patch_attr(hub, "CACHE_DIR", self.path("cache"))
        self.patch_attr(update, "__version__", "1.0.0")

    def test_what_the_last_check_found_survives_a_restart(self):
        with fake_urlopen(RELEASE):
            update.check()
        release = update.pending()
        self.assertEqual(release.version, "1.4.0")
        self.assertEqual(release.url, RELEASE["html_url"])

    def test_nothing_was_ever_checked(self):
        self.assertIsNone(update.pending())
        self.assertEqual(update.state(), {})
        self.assertTrue(update.due())

    def test_a_release_that_is_no_longer_newer_is_not_pending(self):
        """The state file outlives the build that wrote it: an update that was
        found and then installed must not still be waiting afterwards."""
        update._store(version="1.4.0")
        self.patch_attr(update, "__version__", "1.4.0")
        self.assertIsNone(update.pending())

    def test_a_version_is_announced_once(self):
        self.assertEqual(update.announced(), "")
        update.mark_announced("1.4.0")
        self.assertEqual(update.announced(), "1.4.0")

    def test_a_state_file_that_is_rubbish_is_no_state_at_all(self):
        update.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        update.STATE_FILE.write_text("half a {", encoding="utf-8")
        self.assertEqual(update.state(), {})
        self.assertIsNone(update.pending())

    def test_a_state_file_that_cannot_be_written_is_not_a_failure(self):
        self.patch_attr(update, "STATE_FILE",
                        self.path("nope") / "deeper" / "update.json")
        self.path("nope").write_text("a file where a directory would go")
        with fake_urlopen(RELEASE):
            release = update.check()
        self.assertEqual(release.version, "1.4.0")

    def test_the_clock_is_kept_out_of_the_settings(self):
        """A background check writes while the settings window may be open, and
        a write into config.json there would undo whatever it holds."""
        with fake_urlopen(RELEASE):
            update.check()
        stored = json.loads(update.STATE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(stored["version"], "1.4.0")
        self.assertGreater(stored["checked"], 0)
