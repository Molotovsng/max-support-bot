from __future__ import annotations

from typing import Any

from constants import (
    BUTTON_BACK_TO_START,
    BUTTON_SEND_ANONYMOUS,
    BUTTON_SEND_IDENTIFIED,
    BUTTON_USER_CONTRACTOR,
    BUTTON_USER_EMPLOYEE,
    BUTTON_USER_INDIVIDUAL,
    DEPARTMENTS,
)


def message_button(text: str) -> dict[str, Any]:
    return {
        "type": "message",
        "text": text,
    }


def inline_keyboard(rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": rows,
            },
        }
    ]


def department_keyboard() -> list[dict[str, Any]]:
    return inline_keyboard([[message_button(label)] for label in DEPARTMENTS.values()])


def user_type_keyboard() -> list[dict[str, Any]]:
    return inline_keyboard(
        [
            [message_button(BUTTON_USER_EMPLOYEE)],
            [message_button(BUTTON_USER_CONTRACTOR)],
            [message_button(BUTTON_USER_INDIVIDUAL)],
            [message_button(BUTTON_BACK_TO_START)],
        ]
    )


def contact_mode_keyboard() -> list[dict[str, Any]]:
    return inline_keyboard(
        [
            [message_button(BUTTON_SEND_ANONYMOUS)],
            [message_button(BUTTON_SEND_IDENTIFIED)],
            [message_button(BUTTON_BACK_TO_START)],
        ]
    )


def back_to_menu_keyboard() -> list[dict[str, Any]]:
    return inline_keyboard([[message_button(BUTTON_BACK_TO_START)]])
