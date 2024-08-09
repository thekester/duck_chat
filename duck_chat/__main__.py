import sys
import asyncio
from duck_chat.gui import ChatApp  # Importation absolue
from duck_chat.cli import CLI  # Importation absolue

def main():
    if hasattr(sys, 'frozen'):  # Detect if running in PyInstaller bundle
        # Launch the GUI directly if running as a .exe
        launch_gui()
    else:
        # When running as a script, allow CLI or GUI choice
        print("Welcome to Duck Chat AI")
        print("Choose your mode:")
        print("1: Command Line Interface (CLI)")
        print("2: Graphical User Interface (GUI)")

        choice = input("Enter 1 or 2: ").strip()

        if choice == "1":
            # Launch CLI
            asyncio.run(CLI().run())
        elif choice == "2":
            # Launch GUI
            launch_gui()
        else:
            print("Invalid choice. Please enter 1 or 2.")
            sys.exit(1)

def launch_gui():
    ChatApp().run()

if __name__ == "__main__":
    main()
