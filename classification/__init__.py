# classification/__init__.py

"""
Top-level package for the project.
Avoid importing heavy submodules at package import time to keep imports safe for tests.
"""

__all__ = ["__version__"]
__version__ = "0.0.0"

# Optionally provide lazy accessors for subpackages (optional)
# Do NOT import subpackages here to avoid import-time side effects.
# If you need convenience imports, import them lazily in user code:
#   from classification import pipeline  # this will import pipeline then


# """Classification package for audio classification tasks."""

# from . import backbones
# from . import core
# from . import head
# from . import pipeline
# from . import scripts

# __all__ = [
#     "backbones",
#     "core",
#     "head",
#     "pipeline",
#     "scripts"
# ]