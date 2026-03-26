"""Tests for local address -> scriptPubKey conversion in wallet verification."""

from __future__ import annotations

import pytest

from web.services.wallet_verification import _address_to_script_pub_key


def test_address_to_script_pub_key_supports_p2pkh() -> None:
    script = _address_to_script_pub_key("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    assert script.hex() == "76a91462e907b15cbf27d5425399ebf6f0fb50ebb88f1888ac"


def test_address_to_script_pub_key_supports_p2sh() -> None:
    script = _address_to_script_pub_key("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy")
    assert script.hex() == "a914b472a266d0bd89c13706a4132ccfb16f7c3b9fcb87"


def test_address_to_script_pub_key_rejects_invalid_address() -> None:
    with pytest.raises(RuntimeError):
        _address_to_script_pub_key("not-a-bitcoin-address")
