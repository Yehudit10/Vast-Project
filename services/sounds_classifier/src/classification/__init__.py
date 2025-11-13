"""
Top-level package for the project.
Avoid importing heavy submodules at package import time to keep imports safe for tests.
"""

__all__ = ["__version__"]
__version__ = "0.0.0"