"""Allow `python -m pitcrew` to invoke the CLI."""
import sys
from pitcrew.cli import main

sys.exit(main())
