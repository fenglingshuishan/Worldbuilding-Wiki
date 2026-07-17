from __future__ import annotations

from worldbuilding_wiki.cli import _configure_utf8


class FakeStream:
    def __init__(self) -> None:
        self.configuration: dict[str, str] = {}

    def reconfigure(self, **configuration: str) -> None:
        self.configuration = configuration


def test_cli_configures_utf8_output_for_non_chinese_windows_locales() -> None:
    stream = FakeStream()

    _configure_utf8(stream)

    assert stream.configuration == {"encoding": "utf-8", "errors": "replace"}
