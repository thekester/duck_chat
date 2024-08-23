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
from datetime import datetime, timedelta
import asyncio
import threading
import os
import sys
import aiohttp
import glob
import logging
from enum import Enum

# Modèles disponibles
class ModelType(Enum):
    GPT4o = "gpt-4o-mini"
    Claude = "claude-3-haiku-20240307"
    Llama = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
    Mixtral = "mistralai/Mixtral-8x7B-Instruct-v0.1"

from duck_chat.api import DuckChat, DuckChatException
from .models.models import Role, SavedHistory, History

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure the savedhistory directory exists
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
    """Parcourir le dossier des conversations sauvegardées et retourner une liste de chemins de fichiers."""
    logger.info(f"Welcome to load_saved_conversations")

    logger.info(f"Searching for saved conversations in directory: {directory}")
    
    history_files = glob.glob(os.path.join(directory, "history_*.json"))
    logger.info(f"Found {len(history_files)} saved conversation files.")
    
    if not history_files:
        logger.error("No saved conversations were found. Please ensure there are files in the directory.")
    
    for file in history_files:
        logger.info(f"Adding file to saved_history_files: {file}")
    
    return history_files  # Retourne la liste des chemins des fichiers de conversation

class SelectableRecycleBoxLayout(FocusBehavior, LayoutSelectionBehavior, RecycleBoxLayout):
    """Adds selection and focus behavior to the RecycleView's BoxLayout"""

class SelectableLabel(RecycleDataViewBehavior, Label):
    """Add selection support to the Label inside the RecycleView"""
    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)

    def refresh_view_attrs(self, rv, index, data):
        """Catch and handle the view changes"""
        self.index = index
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
                conversation_path = app.saved_history_files[index]  # Récupère le chemin du fichier correspondant
                app.load_conversation(conversation_path)  # Charge la conversation
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
                self.data.append({'text': os.path.basename(file_path).split('.')[0].replace('history_', '')})
        else:
            self.update_no_conversations_message()

        self.refresh_from_data()  # Refresh the view to display the updated data
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

        # Main layout with two panels: history and chat
        main_layout = BoxLayout(orientation='horizontal')

        # Left panel for saved history
        left_panel = BoxLayout(orientation='vertical', size_hint=(0.3, 1))
        
        # Add "Saved History" header
        header_label = Label(text="Saved History", size_hint=(1, None), height=dp(40), halign="center", valign="middle")
        left_panel.add_widget(header_label)

        # Initialize the list of saved conversation files
        self.saved_history_files = load_saved_conversations(SAVE_DIR)

        # Initialize HistoryRecycleView with the saved files
        self.history_view = HistoryRecycleView(saved_history_files=self.saved_history_files, size_hint=(1, 1))
        left_panel.add_widget(self.history_view)

        # Add left panel to the main layout
        main_layout.add_widget(left_panel)

        # Right panel for chat interface
        right_panel = BoxLayout(orientation='vertical', size_hint=(0.7, 1))

        # Add model selector at the top
        self.model_selector = Spinner(
            text=ModelType.Llama.value,  # Llama selected by default
            values=[model.value for model in ModelType],
            size_hint=(None, None),
            size=(300, 44),
            pos_hint={'center_x': 0.5},
        )
        right_panel.add_widget(self.model_selector)

        # Chat and input layout
        self.chat_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        right_panel.add_widget(self.chat_layout)

        self.setup_chat_interface()

        # Add right panel to the main layout
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

            # Add the error message layout above the chat display
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
        if message.strip():
            self.display_message(f"You: {message}", user=True)
            self.user_input.text = ""
            
            async def get_response():
                try:
                    # Add user's message to the history
                    self.chat_client.saved_history.add_input(message)
                    
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
            model_type = ModelType(selected_model)
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


if __name__ == "__main__":
    ChatApp().run()
