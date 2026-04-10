if __name__ == "__main__":
    try:
        from .app import main
    except ModuleNotFoundError as exc:
        missing = str(exc.name or "")
        if missing.startswith("PySide6"):
            raise SystemExit(
                "PySide6 nao esta instalado. Rode `pip install -r ferramentas/requirements.txt`."
            ) from exc
        raise
    raise SystemExit(main())
