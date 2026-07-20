"""PyInstaller launcher that preserves AM Configurator's package context."""

from am_configurator.desktop import main


if __name__ == "__main__":
    raise SystemExit(main())
