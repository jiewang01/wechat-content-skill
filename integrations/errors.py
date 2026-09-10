"""集成层共享异常：所有 Provider 对外只抛 ProviderError（蓝图十八章⑤）。

上层（Skill / Workflow）不需要区分网络错误、HTTP 状态码、响应解析错误——
统一捕获 ProviderError 即可走降级分支（蓝图十二章）。
"""

from __future__ import annotations


class ProviderError(Exception):
    """Provider 调用失败（网络 / 鉴权 / 限流 / 响应异常）的统一封装。

    errcode 携带平台业务错误码（微信 40001/42001 表示 token 失效），
    供上层做定向重试；其余 Provider 场景保持 None。
    """

    def __init__(self, message: str, *, errcode: int | None = None) -> None:
        super().__init__(message)
        self.errcode = errcode
