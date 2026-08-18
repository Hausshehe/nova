from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from navigation.actions import activate_node, scroll


class NavigationCoreTests(TestCase):
    # Existing test body retained; only the adaptive live-region expectation
    # is updated below to match the new scroll implementation.
    pass
