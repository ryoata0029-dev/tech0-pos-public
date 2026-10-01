"""Public failures never contain SQL, credentials or cookie values."""


class PosError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message


def unauthenticated() -> PosError:
    return PosError(401, "UNAUTHENTICATED", "担当者IDまたはパスワードが正しくありません")


def forbidden() -> PosError:
    return PosError(
        403, "FORBIDDEN", "認証または復帰情報を確認できません。本人による確認が必要です。"
    )


def conflict(code: str = "STATE_CONFLICT") -> PosError:
    return PosError(409, code, "操作を停止しました。状態を確認してください。")


def unavailable() -> PosError:
    return PosError(
        503, "SERVICE_UNAVAILABLE", "状態を確認できません。内容を保持して停止してください。"
    )
