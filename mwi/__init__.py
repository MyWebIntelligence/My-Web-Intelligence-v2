"""
MyWebIntelligence main module

Deliberately empty of re-exports. `from .cli import command_input` used to
sit here with no consumer (checked across tests, scripts, mywi.py and docs),
and it made `import mwi` drag in the whole CLI — argparse, every controller,
every pipeline — for anything that only wanted `mwi.model`.
"""
