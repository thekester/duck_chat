from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.recycleview.layout import LayoutSelectionBehavior
from kivy.properties import BooleanProperty
from kivy.metrics import dp
import os
import platform
import glob
import logging
from enum import Enum
import asyncio
import threading
import aiohttp
from duck_chat.api import DuckChat, DuckChatException
from .models.models import Role, SavedHistory, History
import sys
import datetime
from datetime import timedelta

# Importing MyWidget for file selection
from .MyWidget import MyWidget


# Available Models
class ModelType(Enum):
    GPT4o = "gpt-4o-mini"
    Claude = "claude-3-haiku-20240307"
    Llama = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
    Mixtral = "mistralai/Mixtral-8x7B-Instruct-v0.1"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure the saved history directory exists
SAVE_DIR = os.path.join(os.path.dirname(__file__), '..', 'savedhistory')
logger.info(f"Saving histories in directory: {os.path.abspath(SAVE_DIR)}")
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

def resource_path(relative_path):
    """Get the absolute path to the resource, works for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

def get_current_datetime(days_offset=0):
    """Function to get the current date and time with an optional offset in days"""
    target_date = datetime.now() + timedelta(days=days_offset)
    return target_date.strftime("%Y-%m-%d %H:%M:%S")

def load_saved_conversations(directory):
    """Browse the saved conversations folder and return a list of file paths."""
    logger.info(f"Welcome to load_saved_conversations")

    logger.info(f"Searching for saved conversations in directory: {directory}")
    
    history_files = glob.glob(os.path.join(directory, "history_*.json"))
    logger.info(f"Found {len(history_files)} saved conversation files.")
    
    if not history_files:
        logger.error("No saved conversations were found. Please ensure there are files in the directory.")
    
    for file in history_files:
        logger.info(f"Adding file to saved_history_files: {file}")
    
    return history_files  # Return the list of conversation file paths

class SelectableRecycleBoxLayout(FocusBehavior, LayoutSelectionBehavior, RecycleBoxLayout):
    """Adds selection and focus behavior to the RecycleView's BoxLayout"""

class SelectableLabel(RecycleDataViewBehavior, Label):
    """Add selection support to the Label inside the RecycleView"""
    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self.text = data['text']
        self.color = (1, 1, 1, 1)  # Set text color to white for visibility
        self.size_hint_y = None  # Disable automatic size hint for height
        self.height = dp(40)  # Set a minimum height for the label
        self.text_size = (self.width, None)  # Allow the text to wrap if needed
        self.halign = 'left'  # Align text to the left

        # For testing visibility, adding background color to the label
        self.canvas.before.clear()  # Clear any previous instructions
        with self.canvas.before:
            Color(0.5, 0.5, 0.5, 1)  # Light gray background
            self.rect = RoundedRectangle(size=self.size, pos=self.pos)
        self.bind(pos=lambda instance, value: setattr(self.rect, 'pos', value),
                  size=lambda instance, value: setattr(self.rect, 'size', value))

        return super(SelectableLabel, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        """Add selection on touch down"""
        if super(SelectableLabel, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            return self.parent.select_with_touch(self.index, touch)
        return False

    def apply_selection(self, rv, index, is_selected):
        self.selected = is_selected
        if is_selected:
            app = App.get_running_app()
            if index < len(app.saved_history_files):
                conversation_path = app.saved_history_files[index]  # Retrieve the corresponding file path
                app.load_conversation(conversation_path)  # Load the conversation
            else:
                logger.error(f"Invalid index {index} for saved_history_files with length {len(app.saved_history_files)}")

class HistoryRecycleView(RecycleView):
    """RecycleView to display a list of saved conversations"""

    def __init__(self, saved_history_files, **kwargs):
        super(HistoryRecycleView, self).__init__(**kwargs)
        self.saved_history_files = saved_history_files  # Store the list of file paths

        # Create and add the layout manager directly within the RecycleView
        self.layout_manager = SelectableRecycleBoxLayout(
            default_size=(None, dp(56)),
            default_size_hint=(1, None),
            size_hint_y=None,
            orientation='vertical'
        )
        self.add_widget(self.layout_manager)  # Ensure layout_manager is added to RecycleView
        self.viewclass = 'SelectableLabel'  # Ensure the view class is set

        # Update the list based on the provided files
        self.update_conversations_list()

    def update_conversations_list(self):
        """Update the conversation list with the saved history files"""
        if self.saved_history_files:
            self.data = [{'text': 'Saved History', 'selectable': False}]
            for file_path in self.saved_history_files:
                file_name = os.path.basename(file_path).replace('.json', '')
                self.data.append({'text': file_name})
        else:
            self.data = [{'text': 'No saved conversations found.', 'selectable': False}]
        
        self.refresh_from_data()
        logger.info("HistoryRecycleView updated with saved conversations.")

    def update_no_conversations_message(self, message=None):
        """Update the default message when no saved conversations are found"""
        if message is None:
            message = 'No saved conversations found.'
        self.data = [{'text': message, 'selectable': False}]
        self.layout_manager.clear_selection()  # Clear any previous selection in the list
        self.refresh_from_data()  # Refresh the view to ensure the message is displayed
        logger.info("HistoryRecycleView updated with 'No Saved History' message.")

class ChatApp(App):

    def build(self):
        # Initialize an event loop to be used for asyncio tasks
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Initialize chat client and interface components
        self.chat_client = None
        self.selected_files = []  # Store selected files

        # Main layout with two panels: history and chat
        main_layout = BoxLayout(orientation='horizontal')  # Changed to horizontal to add a left panel

        # Left panel for Saved History
        left_panel = BoxLayout(orientation='vertical', size_hint=(0.3, 1))  # 30% of the screen for saved history

        # Label for the Saved History section
        history_label = Label(text="Saved History", size_hint_y=None, height=dp(40))
        left_panel.add_widget(history_label)

        # Initialize the list of saved conversation files
        self.saved_history_files = load_saved_conversations(SAVE_DIR)

        # Initialize HistoryRecycleView with the saved files
        self.history_view = HistoryRecycleView(saved_history_files=self.saved_history_files, size_hint=(1, 1))
        left_panel.add_widget(self.history_view)

        main_layout.add_widget(left_panel)

        # Right panel for chat and other interface components
        right_panel = BoxLayout(orientation='vertical', size_hint=(0.7, 1))  # 70% of the screen for the chat

        # Model selection dropdown
        self.model_selector = Spinner(
            text=ModelType.Llama.name,  # Llama selected by default
            values=[model.name for model in ModelType],  # Use names here
            size_hint=(None, None),
            size=(300, 44),
            pos_hint={'center_x': 0.5},
        )
        right_panel.add_widget(self.model_selector)

        self.chat_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        right_panel.add_widget(self.chat_layout)

        # File selection button
        file_button = Button(text="Import Files", size_hint=(None, None), size=(150, 50))
        file_button.bind(on_press=self.open_file_chooser)
        right_panel.add_widget(file_button)

        # Area to display selected files within a ScrollView
        scroll_view = ScrollView(size_hint=(1, 0.2))
        self.selected_files_layout = BoxLayout(orientation='vertical', padding=10, spacing=10, size_hint_y=None)
        self.selected_files_layout.bind(minimum_height=self.selected_files_layout.setter('height'))
        scroll_view.add_widget(self.selected_files_layout)
        right_panel.add_widget(scroll_view)

        self.setup_chat_interface()

        main_layout.add_widget(right_panel)

        # Initialize the chat client and then update the history list
        self.initialize_chat_client()
        self.update_history_list()

        return main_layout

    def setup_chat_interface(self):
        """Set up the chat interface components"""

        # Chat display area
        self.chat_display_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=10)
        self.chat_display_layout.bind(minimum_height=self.chat_display_layout.setter('height'))

        self.chat_display = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.chat_display.add_widget(self.chat_display_layout)

        self.chat_layout.add_widget(self.chat_display)

        # User input area
        input_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)

        self.user_input = TextInput(size_hint_y=None, height=44, multiline=False)
        input_layout.add_widget(self.user_input)

        self.send_button = Button(
            background_normal=resource_path('images/send_icon.png'),
            size_hint=(None, None),
            size=(46, 37)
        )
        self.send_button.bind(on_press=self.send_message)
        input_layout.add_widget(self.send_button)

        self.chat_layout.add_widget(input_layout)

    def show_error(self, message):
        """Display an error message in the error banner"""
        if not hasattr(self, 'error_message_layout'):
            # Create and add the error banner
            self.error_message_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(50))
            self.error_message_label = Label(size_hint_x=0.9, halign="left", valign="middle", color=(1, 1, 1, 1))
            self.error_message_layout.add_widget(self.error_message_label)

            close_button = Button(text="X", size_hint_x=0.1, on_release=self.dismiss_error)
            self.error_message_layout.add_widget(close_button)

            # Add the error message layout above the model selector
            self.chat_layout.add_widget(self.error_message_layout, index=0)

        self.error_message_label.text = message
        with self.error_message_layout.canvas.before:
            Color(1, 0, 0, 1)  # Red background
            self.rect = RoundedRectangle(size=self.error_message_layout.size, pos=self.error_message_layout.pos, radius=[10])
            self.error_message_layout.bind(pos=lambda instance, value: setattr(self.rect, 'pos', value),
                                           size=lambda instance, value: setattr(self.rect, 'size', value))

    def dismiss_error(self, instance):
        """Dismiss the error banner and remove it from the layout"""
        if hasattr(self, 'error_message_layout'):
            self.chat_layout.remove_widget(self.error_message_layout)
            del self.error_message_layout  # Clean up the reference to allow garbage collection

    def load_conversation(self, conversation_path):
        """Load a conversation from its file path"""
        self.chat_display_layout.clear_widgets()
        try:
            conv_id = os.path.basename(conversation_path).replace('history_', '').replace('.json', '')
            saved_history = SavedHistory.load(conv_id)
            for message in saved_history.messages:
                user = message.role == Role.user
                self.display_message(f"{'You' if user else 'AI'}: {message.content}", user=user)
            logger.info(f"Loaded conversation from {conversation_path}")
        except FileNotFoundError:
            error_message = f"Error: Conversation file {conversation_path} not found."
            self.display_message(error_message, user=False)
            logger.error(error_message)

    def send_message(self, instance):
        """Send a message and handle the response"""
        self.animate_send_button()

        if not self.chat_client:
            self.initialize_chat_client()

        message = self.user_input.text
        if message.strip() or self.selected_files:
            if message.startswith("/"):
                # Handle slash commands
                self.handle_command(message)
            else:
                # Proceed with sending a normal message
                if message.strip():
                    self.display_message(f"You: {message}", user=True)
                if self.selected_files:
                    for file_path in self.selected_files:
                        self.display_message(f"File attached: {os.path.basename(file_path)}", user=True)
                
                self.user_input.text = ""

                async def get_response():
                    try:
                        # Add user's message and files to the history
                        if message.strip():
                            self.chat_client.saved_history.add_input(message)
                        
                        for file_path in self.selected_files:
                            # Implement logic to read the file and process it
                            with open(file_path, 'r') as f:
                                file_content = f.read()  # This is an example for text files
                            self.chat_client.saved_history.add_input(f"[FILE CONTENT]: {file_content}")
                        
                        # Get the response from the AI
                        response = await self.chat_client.ask_question(message)
                        
                        # Add AI's response to the history
                        self.chat_client.saved_history.add_answer(response)
                        
                        # Display the response
                        self.display_message(f"AI: {response}", user=False)
                        
                        # Save the history automatically after each interaction
                        self.chat_client.saved_history.save()

                    except DuckChatException as e:
                        if str(e) != "Session closed before completing the request.":
                            self.display_message(f"Error: {str(e)}", user=False)

                # Execute the async function in a separate thread
                self.response_thread = threading.Thread(target=lambda: self.loop.run_until_complete(get_response()))
                self.response_thread.start()

            # Clear selected files after sending
            self.selected_files = []
            self.update_selected_files_display()

    def display_message(self, message, user=False):
        """Display a message in the chat display area"""
        Clock.schedule_once(lambda dt: self._add_message_to_display(message, user))

    def _add_message_to_display(self, message, user):
        """Internal method to add a message to the chat display area"""
        message_layout = BoxLayout(
            orientation='horizontal', 
            size_hint_y=None, 
            padding=10, 
            spacing=10
        )

        # Label for the message
        label = Label(
            text=message,
            size_hint=(None, None),
            text_size=(self.root.width * 0.6, None),  # Maximum width of 60% of the screen
            halign='left' if not user else 'right',
            valign='middle',
            padding=(10, 10),
            color=(0.93, 0.95, 0.96, 1) if not user else (0.88, 0.95, 0.94, 1)  # Softer text color
        )

        # Calculate the label's width and height based on content
        label.texture_update()
        label.width = max(150, min(self.root.width * 0.6, label.texture_size[0] + 20))
        label.height = label.texture_size[1] + 20  # Dynamic height adjustment

        # Background color with rounded corners and placement
        with label.canvas.before:
            if user:
                Color(0.16, 0.61, 0.56, 1)  # Darker teal
            else:
                Color(0.15, 0.27, 0.32, 1)  # Dark slate gray

            rect = RoundedRectangle(size=label.size, pos=label.pos, radius=[10,])
            label.bind(pos=lambda instance, value: setattr(rect, 'pos', value),
                    size=lambda instance, value: setattr(rect, 'size', value))

        # Add the label and the image (either user or bot)
        if user:
            message_layout.add_widget(Widget())  # Empty space on the left for user messages
            message_layout.add_widget(label)
            message_layout.add_widget(Image(source=resource_path('images/human.png'), size_hint=(None, None), size=(25, 27)))
        else:
            message_layout.add_widget(Image(source=resource_path('images/aichatbot25x26.png'), size_hint=(None, None), size=(44, 44)))
            message_layout.add_widget(label)
            message_layout.add_widget(Widget())  # Empty space on the right for bot messages

        # Set the size of the message_layout to ensure it fits the content properly
        message_layout.height = label.height + 20  # Adding padding to prevent overlap

        # Add the message layout to the chat display
        self.chat_display_layout.add_widget(message_layout)
        self.chat_display_layout.height += message_layout.height  # Increase layout height
        self.chat_display.scroll_to(message_layout)

        # Add animation here
        self.animate_message(message_layout)

    def animate_message(self, message_widget):
        """Animate the appearance of a message"""
        animation = Animation(size=(message_widget.width, 0), opacity=0, duration=0) + \
                    Animation(size=(message_widget.width, message_widget.height), opacity=1, duration=0.3)

        # Start the animation on the message widget
        animation.start(message_widget)

    def animate_send_button(self):
        """Animate the send button when pressed"""
        animation = Animation(size=(self.send_button.width * 0.9, self.send_button.height * 0.9), duration=0.1) + \
                    Animation(size=(self.send_button.width, self.send_button.height), duration=0.1)
        animation.start(self.send_button)

    def initialize_chat_client(self):
        """Initialize the chat client with the selected model"""
        selected_model = self.model_selector.text

        if selected_model == 'Select Model':
            self.show_error("Please select a model from the dropdown before proceeding.")
            return

        try:
            model_type = ModelType[selected_model]
            self.chat_client = DuckChat(model=model_type, session=aiohttp.ClientSession(loop=self.loop))
            
            # Load history and update the history list
            self.update_history_list()

        except ValueError:
            self.show_error("Invalid model selected. Please select a valid model.")

    def update_history_list(self):
        """Update the history list in the side panel"""
        logger.info(f"Looking for conversation histories in: {SAVE_DIR}")
        
        if self.chat_client:
            # Appel à la fonction pour charger les fichiers d'historique
            self.saved_history_files = load_saved_conversations(SAVE_DIR)
            logger.info(f"Found history files: {self.saved_history_files}")
            
            # Initialize the data list with a header message
            if self.saved_history_files:
                self.history_view.data = [{'text': 'Saved History', 'selectable': False}]
                logger.info("Appending 'Saved History' to the HistoryRecycleView.")
                
                # Add each history file to the list
                for file_path in self.saved_history_files:
                    file_name = os.path.basename(file_path).split('.')[0].replace('history_', '')
                    logger.info(f"Adding {file_name} to history view")
                    self.history_view.data.append({'text': file_name})
                
                logger.info(f"History list updated with {len(self.saved_history_files)} items.")
            else:
                # Display a message indicating no saved history
                self.history_view.data = [{'text': 'No Saved History', 'selectable': False}]
                logger.warning(f"No saved conversations found in the directory: {SAVE_DIR}")
                logger.info("Appending 'No Saved History' to the HistoryRecycleView.")
            
            # Refresh the view to display the updated data
            logger.info(f"Refreshing history view with data: {self.history_view.data}")
            self.history_view.refresh_from_data()
            logger.info("HistoryRecycleView refreshed.")

    def handle_command(self, command):
        """Handle custom slash commands"""
        args = command.split()
        command_name = args[0][1:]

        if command_name == "help":
            help_message = (
                "Available Commands:\n"
                "- /help             : Display this help message\n"
                "- /singleline       : Switch to singleline mode, validate is done by <enter>\n"
                "- /multiline        : Switch to multiline mode, validate is done by EOF <Ctrl+D>\n"
                "- /stream_on        : Enable stream mode\n"
                "- /stream_off       : Disable stream mode\n"
                "- /quit             : Quit the application\n"
                "- /retry [count]    : Regenerate the answer for the specified prompt (default /retry 1)\n"
                "- /save             : Save the current conversation history\n"
                "- /load [ID]        : Load a conversation history by ID\n"
                "- /list_histories   : List all saved conversation histories\n"
            )
            self.display_message(help_message, user=False)
        
        elif command_name == "singleline":
            self.display_message("Switched to singleline mode", user=False)
            # Ici, tu pourrais implémenter la logique pour changer le mode d'entrée
            # self.INPUT_MODE = "singleline"

        elif command_name == "multiline":
            self.display_message("Switched to multiline mode", user=False)
            # Ici, tu pourrais implémenter la logique pour changer le mode d'entrée
            # self.INPUT_MODE = "multiline"

        elif command_name == "stream_on":
            self.display_message("Switched to stream mode", user=False)
            # Activer le mode streaming
            # self.STREAM_MODE = True

        elif command_name == "stream_off":
            self.display_message("Switched to non-stream mode", user=False)
            # Désactiver le mode streaming
            # self.STREAM_MODE = False

        elif command_name == "quit":
            self.display_message("Quitting application", user=False)
            self.stop()  # Quitter l'application

        elif command_name == "retry":
            if len(args) < 2:
                count = 1  # Valeur par défaut si aucun argument n'est fourni
            else:
                try:
                    count = int(args[1])
                except ValueError:
                    self.display_message("Invalid retry count. Must be an integer.", user=False)
                    return

            if count < 1:
                self.display_message("Retry count must be greater than zero.", user=False)
                return
            
            # Logique pour reposer la question avec `count` comme index
            self.display_message(f"Retrying response for input #{count}", user=False)
            # async logic could be implemented if needed

        elif command_name == "save":
            try:
                self.chat_client.saved_history.save()
                self.display_message(f"History saved with ID: {self.chat_client.saved_history.id}", user=False)
            except Exception as e:
                self.display_message(f"Error saving history: {str(e)}", user=False)

        elif command_name == "load":
            if len(args) < 2:
                self.display_message("You must provide an ID to load.", user=False)
            else:
                history_id = args[1]
                try:
                    self.chat_client.history = DuckChat.load_history(history_id)
                    self.display_message(f"Loaded history with ID: {history_id}", user=False)
                except FileNotFoundError:
                    self.display_message(f"No history found with ID: {history_id}", user=False)

        elif command_name == "list_histories":
            histories = glob.glob("history_*.json")
            if not histories:
                self.display_message("No histories found.", user=False)
            else:
                history_list = "\n".join(histories)
                self.display_message(f"Saved Histories:\n{history_list}", user=False)

        else:
            self.display_message(f"Unknown command: {command}. Type /help for available commands.", user=False)


    def on_stop(self):
        """This method is called when the application is closed"""
        if self.chat_client:
            if hasattr(self, 'response_thread') and self.response_thread.is_alive():
                # Wait for the response thread to finish
                self.response_thread.join()
            # Save the history one last time before closing
            self.chat_client.saved_history.save()
            self.loop.run_until_complete(self.chat_client.close_session())
        self.loop.close()

    def open_file_chooser(self, instance):
        """Open the file chooser using MyWidget."""
        file_widget = MyWidget()
        file_widget.open_file_chooser()

        # Handle file selection in MyWidget (you can pass a callback to handle selections)
        file_widget.load_selected_files = self.load_selected_files

    def load_selected_files(self, selection, popup):
        """Load the selected files and update the UI."""
        popup.dismiss()
        self.selected_files = selection
        self.update_selected_files_display()

    def update_selected_files_display(self):
        """Update the display with the list of selected files."""
        self.selected_files_layout.clear_widgets()
        if self.selected_files:
            for file_path in self.selected_files:
                file_label = Label(text=os.path.basename(file_path), size_hint_y=None, height=dp(30))
                self.selected_files_layout.add_widget(file_label)
        else:
            self.selected_files_layout.add_widget(Label(text="No files selected.", size_hint_y=None, height=dp(30)))


if __name__ == "__main__":
    ChatApp().run()
