"""Точка входа: запуск из исходников (start.sh / start.bat) или из .exe/.app."""
import customtkinter as ctk

from ui.app import App


def main() -> None:
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
