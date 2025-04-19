from concurrent.futures import ThreadPoolExecutor
from tkinter import Tk
from tkinter.filedialog import askopenfile
from tkinter.messagebox import askyesno
from typing import Any, Iterable


def ask_for_confirmation(title: str, message: str) -> bool:
    with ThreadPoolExecutor() as executor:

        def ask() -> bool:
            root = Tk()
            root.withdraw()
            answer = askyesno(title=title, message=message)
            root.destroy()
            return answer

        return executor.submit(ask).result()


def open_ask_file_dialog(
    filetypes: Iterable[tuple[str, str | list[str] | tuple[str, ...]]] | None = [
        ("PSD", "psd")
    ],
    *args: Any,
    **kwargs: Any,
):
    with ThreadPoolExecutor() as executor:

        def ask() -> str | None:
            root = Tk()
            root.withdraw()
            file = askopenfile(filetypes=filetypes, *args, **kwargs)
            root.destroy()
            return file.name if file else None

        return executor.submit(ask).result()
