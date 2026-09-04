"""Agent-facing entrypoints: validate, brief, export, the task lifecycle, CRUD.

A real package, imported as ``specy_road.bundled_scripts.<name>``. These used to
be imported by bare module name, which worked only because eleven modules
mutated ``sys.path`` on the way past -- ``ensure_bundled_scripts_on_path()`` at
twenty-four call sites, plus seven hand-rolled equivalents with different
variable names, plus a ``PYTHONPATH`` prefix built in ``cli._run`` and again in
``tests/helpers``. Exactly one of those honoured ``SPECY_ROAD_SCRIPTS``, so
setting it produced a half-redirected process.
"""
