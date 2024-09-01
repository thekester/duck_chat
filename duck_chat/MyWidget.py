from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserIconView
import os

class MyWidget(GridLayout):
    def __init__(self, **kwargs):
        super(MyWidget, self).__init__(**kwargs)
        self.cols = 1

    def open_file_chooser(self):
        """Open a file chooser in a popup to select files with icon view."""
        layout = GridLayout(cols=1, spacing=10, size_hint=(1, 1))
        layout.bind(minimum_height=layout.setter('height'))

        # Set the initial path to the user's home directory
        initial_path = os.path.expanduser('~')
        filechooser = FileChooserIconView(multiselect=True, path=initial_path, show_hidden=True, size_hint=(1, 1))
        layout.add_widget(filechooser)

        select_button = Button(text="Select", size_hint_y=None, height=50)
        layout.add_widget(select_button)

        popup = Popup(title="Select Files", content=layout, size_hint=(0.9, 0.9), auto_dismiss=False)

        # Bind the select button to load and display selected files
        select_button.bind(on_release=lambda x: self.load_selected_files(filechooser.selection, popup))

        popup.open()

    def load_selected_files(self, selection, popup):
        """Load and display selected files."""
        popup.dismiss()

        if selection:
            # This is just an example of how to handle the selected files
            # In a real application, you might want to do something else
            print(f"Selected files: {selection}")
        else:
            print("No file selected")

class FileChooserWindow(App):
    def build(self):
        widget = MyWidget()
        widget.open_file_chooser()  # Automatically open the file chooser when the app starts
        return widget

if __name__ == "__main__":
    window = FileChooserWindow()
    window.run()
