import os
import platform
import subprocess


def open_pdf_viewer(pdf_path: str) -> None:
    system = platform.system()
    if system == "Windows":
        os.startfile(pdf_path)
    elif system == "Darwin":
        subprocess.run(["open", pdf_path], check=False)
    else:
        subprocess.run(["xdg-open", pdf_path], check=False)


def request_approval(topic: str, to_list: list[str], cc_list: list[str], pdf_paths: list[str]) -> str:
    print(f'\nReport ready: "{topic}"')
    print(f"\nTo:  {', '.join(to_list)}")
    print(f"CC:  {', '.join(cc_list) if cc_list else '(none)'}")
    for path in pdf_paths:
        print(f"PDF: {path}")
    print()

    while True:
        choice = input("Send this report? [y/n/edit]: ").strip().lower()
        if choice == "y":
            return "approved"
        elif choice == "n":
            return "declined"
        elif choice == "edit":
            open_pdf_viewer(pdf_paths[0])
            print("Review the PDF, then confirm.")
        else:
            print("Please enter y, n, or edit.")
