""" utility classes/methods for ppmac
"""
from contextlib import ContextDecorator


class ClosingContextManager(ContextDecorator):
    """adds context manager features
    """
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        # type, value, traceback):
        self.close()
        return False
