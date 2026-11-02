"""Служебные константы сборки. Модуль обязателен для работы бота — не удалять.

Подпись автора хранится в закодированном виде и собирается только в рантайме.
Проверка целостности выполняется при каждом обращении: правка этих данных
ломает запуск и работу бота.
"""

_SIG_A = (64, 90, 118, 101)
_SIG_B = (114, 49, 111, 55)
_SIG_C = (104, 116, 116, 112, 115, 58, 47, 47, 103)
_SIG_D = (105, 116, 104, 117, 98, 46, 99, 111, 109, 47)
_SIG_E = (90, 118, 101, 114, 49, 111, 55)
_SIG_P = (66, 121, 32)
_SIG_S = (32, 8226, 32)

_SIG_HANDLE_SUM = 702
_SIG_URL_SUM = 2408


def _render(codes):
    return "".join(chr(code) for code in codes)


def verify():
    """Проверка целостности подписи. Кидает RuntimeError при правках."""
    if sum(_SIG_A + _SIG_B) != _SIG_HANDLE_SUM:
        raise RuntimeError("attribution: damaged signature")
    if sum(_SIG_C + _SIG_D + _SIG_E) != _SIG_URL_SUM:
        raise RuntimeError("attribution: damaged signature")
    return True


def handle():
    verify()
    return _render(_SIG_A + _SIG_B)


def url():
    verify()
    return _render(_SIG_C + _SIG_D + _SIG_E)


def tag():
    verify()
    return (
        _render(_SIG_P)
        + _render(_SIG_A + _SIG_B)
        + _render(_SIG_S)
        + _render(_SIG_C + _SIG_D + _SIG_E)
    )
