import functools
import threading
from typing import Callable


def threaded(func: Callable) -> Callable[..., threading.Thread]:
    """Decorator that runs a bound method on a new daemon :class:`threading.Thread`.

    The spawned thread is appended to ``self._threads`` so it can be joined
    during cleanup. The first positional argument of the decorated method must
    be the instance (``self``) and must expose a ``_threads: list`` attribute.

    Args:
        func: The bound method to wrap.

    Returns:
        A wrapper that starts the method on a background thread and returns
        the :class:`threading.Thread` object to the caller.
    """

    @functools.wraps(func)
    def run_as_thread(*args, **kwargs) -> threading.Thread:
        self = args[0]
        if not hasattr(self, "_threads"):
            raise AttributeError(
                f"{type(self).__name__} must define 'self._threads: list[threading.Thread] = []' "
                f"in __init__ to use the @threaded decorator."
            )
        thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        self._threads.append(thread)
        thread.start()
        return thread

    return run_as_thread
