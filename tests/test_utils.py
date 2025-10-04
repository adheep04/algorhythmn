import hashlib

from backend import utils


def test_normalize_name_strips_and_lowercases():
    assert utils.normalize_name("  The Comet  ") == "the comet"


def test_hash_preferences_is_order_insensitive():
    prefs_a = {"love": ["A", "B"], "hate": ["X"]}
    prefs_b = {"love": ["B", "A"], "hate": ["X"]}
    assert utils.hash_preferences(prefs_a) == utils.hash_preferences(prefs_b)
    digest = utils.hash_preferences(prefs_a)
    assert len(digest) == len(hashlib.sha256().hexdigest())


def test_clamp_bounds_values():
    assert utils.clamp(1.5) == 1.0
    assert utils.clamp(-0.2) == 0.0
    assert utils.clamp(0.42) == 0.42
