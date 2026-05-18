import traceback

try:
    from pump_screener.cli import main
    main()
except Exception:
    traceback.print_exc()
finally:
    input("\n  Нажмите Enter для выхода...")
