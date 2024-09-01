import sys
import asyncio
import os
from duck_chat.gui import ChatApp  # Absolute import
from duck_chat.cli import CLI  # Absolute import

def main():
    if getattr(sys, 'frozen', False) or is_android():  # Using getattr for safer checking
        # Launch the GUI directly if running as an executable or on Android
        launch_gui()
    else:
        # When running as a script, allow the choice between CLI or GUI
        launch_interface()

def launch_interface():
    print("Welcome to Duck Chat AI")
    print("Choose your mode:")
    print("1: Command Line Interface (CLI)")
    print("2: Graphical User Interface (GUI)")

    while True:
        choice = input("Enter 1 or 2: ").strip()

        if choice == "1":
            # Launch the CLI
            asyncio.run(CLI().run())
            break
        elif choice == "2":
            # Launch the GUI
            launch_gui()
            break
        else:
            print("Invalid choice. Please enter 1 or 2.")

def launch_gui():
    ChatApp().run()

def is_android():
    # Simple function to check if we are running on Android
    return 'ANDROID_BOOTLOGO' in os.environ

if __name__ == "__main__":
    main()
