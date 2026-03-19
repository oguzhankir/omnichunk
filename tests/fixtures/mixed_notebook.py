# %% [markdown]
"""
# Notebook Title

This notebook demonstrates mixed content.
"""

# %%
import math


def compute(x: float) -> float:
    """Compute something from x.

    This docstring is intentionally long enough to trigger hybrid handling.
    It contains prose-like material and explanation.
    """
    return math.sqrt(x)


# %% [markdown]
"""
## Notes

- Point A
- Point B
"""
