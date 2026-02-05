"""Exchange-specific import parsers.

Each parser module in this package registers itself with the registry
when imported. The imports here ensure all parsers are loaded.
"""

# Import parsers to trigger registration
# Parsers will be added here as they are implemented:
from . import native
from . import coinbase
from . import kraken
from . import strike
from . import river
from . import swan
# from . import cashapp
# from . import gemini
# from . import fold
