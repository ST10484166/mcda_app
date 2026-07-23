"""Entry point for the MCDA tool. Run with: python main.py"""

try:
    from .gui import MCDAApp
except Exception:
    from gui import MCDAApp


def main():
    app = MCDAApp()
    app.mainloop()


if __name__ == "__main__":
    main()
