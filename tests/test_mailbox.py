import pytest

from smtpweb.common.mailbox import sanitize_mailbox_name


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("bob@example.com", "bob@example.com"),
        ("  bob@example.com  ", "bob@example.com"),
        ("Bob@Example.COM", "bob@example.com"),
        ("first.last+tag@sub.example.co.uk", "first.last+tag@sub.example.co.uk"),
    ],
)
def test_valid_addresses_normalized(raw, expected):
    assert sanitize_mailbox_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "not-an-email",
        "@example.com",
        "bob@",
        "bob@ex ample.com",
        "../../etc/passwd@example.com",
        "bob@example.com/../../etc",
        "bob..bad@example.com",
        "bob@example.com\x00",
        "a" * 300 + "@example.com",
    ],
)
def test_invalid_addresses_rejected(raw):
    with pytest.raises(ValueError):
        sanitize_mailbox_name(raw)


def test_max_length_boundary():
    # 254 is the RFC 5321 cap; anything longer must be rejected, anything
    # at or under the cap that's otherwise well-formed must be accepted.
    local = "a" * (254 - len("@example.com"))
    address = f"{local}@example.com"
    assert len(address) == 254
    assert sanitize_mailbox_name(address) == address

    too_long = "a" + address
    with pytest.raises(ValueError):
        sanitize_mailbox_name(too_long)


def test_result_never_contains_path_separators():
    for raw in ["bob@example.com", "a.b+c@sub.example.com"]:
        result = sanitize_mailbox_name(raw)
        assert "/" not in result
        assert "\\" not in result
