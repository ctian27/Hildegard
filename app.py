"""Single entry point for the Hildegard standalone app.

Dispatches on argv so one frozen executable serves both roles:
  - `<exe> --pipeline <args...>`  -> run a surveillance cycle (pipeline.main)
  - `<exe>` (no/other args)       -> launch the GUI

The GUI shells out to this same executable with `--pipeline ...` to run a
cycle, so the run is isolated from the UI and the Stop button can terminate
it -- exactly the subprocess model used when running from source, but without
needing an external Python interpreter.
"""

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--pipeline":
        from pipeline.main import main as pipeline_main
        pipeline_main(sys.argv[2:])
    else:
        from pipeline.gui import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()
