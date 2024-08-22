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

from duck_chat.api import DuckChat, DuckChatException
from .models.models import ModelType, Role, SavedHistory, History

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

class SelectableRecycleBoxLayout(FocusBehavior, LayoutSelectionBehavior, RecycleBoxLayout):
    ''' Adds selection and focus behavior to the view. '''

class SelectableLabel(RecycleDataViewBehavior, Label):
    ''' Add selection support to the Label '''
    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes '''
        self.index = index
        return super(SelectableLabel, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        ''' Add selection on touch down '''
        if super(SelectableLabel, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            return self.parent.select_with_touch(self.index, touch)
        return False

    def apply_selection(self, rv, index, is_selected):
        ''' Respond to the selection of items in the view. '''
        self.selected = is_selected
        if is_selected:
            rv.load_conversation(rv.data[index]['text'])

class HistoryRecycleView(RecycleView):
    def __init__(self, **kwargs):
        super(HistoryRecycleView, self).__init__(**kwargs)
        self.data = []

        # Create and add the layout manager as a child directly within the RecycleView
        layout_manager = SelectableRecycleBoxLayout(
            default_size=(None, dp(56)),
            default_size_hint=(1, None),
            size_hint_y=None,
            height=dp(56) * len(self.data),  # Replace self.minimum_height with a calculated height
            orientation='vertical'
        )
        self.add_widget(layout_manager)
        self.layout_manager = layout_manager

    def load_conversation(self, conv_id):
        self.parent.parent.load_conversation(conv_id)

class ChatApp(App):
    
    def build(self):
        # Initialize an event loop to be used for asyncio tasks
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.chat_client = None

        # Main layout with two panels: history and chat
        main_layout = BoxLayout(orientation='horizontal')

        # History side panel
        self.history_view = HistoryRecycleView(size_hint=(0.3, 1))
        main_layout.add_widget(self.history_view)

        # Chat and input layout
        self.chat_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        main_layout.add_widget(self.chat_layout)

        self.setup_chat_interface()
        return main_layout

    def setup_chat_interface(self):
        # Model selection dropdown
        self.model_selector = Spinner(
            text='Select Model',
            values=[model.value for model in ModelType],
            size_hint=(None, None),
            size=(300, 44),
            pos_hint={'center_x': 0.5},
        )
        self.chat_layout.add_widget(self.model_selector)

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

    def update_history_list(self):
        """Update the history list in the side panel."""
        if self.chat_client:
            self.history_view.data = [{'text': msg.content} for msg in self.chat_client.history.messages]

    def load_conversation(self, conv_id):
        """Load a conversation by its ID."""
        self.chat_display_layout.clear_widgets()
        for message in self.chat_client.history.messages:
            user = message.role == Role.user
            self.display_message(f"{'You' if user else 'AI'}: {message.content}", user=user)

    def send_message(self, instance):
        # Animate the send button
        self.animate_send_button()

        if not self.chat_client:
            self.initialize_chat_client()

        message = self.user_input.text
        if message.strip():
            self.display_message(f"You: {message}", user=True)
            self.user_input.text = ""
            
            async def get_response():
                try:
                    # Initialize a SavedHistory object if not already done
                    if not hasattr(self, 'saved_history'):
                        self.saved_history = SavedHistory(model=self.chat_client.history.model)
                    
                    # Add user's message to the history
                    self.saved_history.add_input(message)
                    
                    # Get the response from the AI
                    response = await self.chat_client.ask_question(message)
                    
                    # Add AI's response to the history
                    self.saved_history.add_answer(response)
                    
                    # Display the response
                    self.display_message(f"AI: {response}", user=False)
                    
                    # Save the conversation history after each interaction
                    self.saved_history.save()

                except DuckChatException as e:
                    self.display_message(f"Error: {str(e)}", user=False)
            
            # Run the async function in a separate thread
            threading.Thread(target=lambda: self.loop.run_until_complete(get_response())).start()


    def display_message(self, message, user=False):
        Clock.schedule_once(lambda dt: self._add_message_to_display(message, user))

    def _add_message_to_display(self, message, user):
        # Layout to contain the message and possibly an image
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
        # The animation starts with a reduced size to 0 and opacity to 0
        animation = Animation(size=(message_widget.width, 0), opacity=0, duration=0) + \
                    Animation(size=(message_widget.width, message_widget.height), opacity=1, duration=0.3)

        # Start the animation on the message widget
        animation.start(message_widget)

    def animate_send_button(self):
        animation = Animation(size=(self.send_button.width * 0.9, self.send_button.height * 0.9), duration=0.1) + \
                    Animation(size=(self.send_button.width, self.send_button.height), duration=0.1)
        animation.start(self.send_button)

    def initialize_chat_client(self):
        selected_model = self.model_selector.text

        if selected_model == 'Select Model':
            self.display_message("Please select a model from the dropdown before proceeding.", user=False)
            return

        try:
            model_type = ModelType(selected_model)
            self.chat_client = DuckChat(model=model_type, session=aiohttp.ClientSession(loop=self.loop))
            
            # Load history and update the history list
            self.update_history_list()

        except ValueError:
            self.display_message("Invalid model selected. Please select a valid model.", user=False)

    def handle_chat_response(self, message):
        message_lower = message.lower()

        if "tomorrow" in message_lower:
            future_datetime = get_current_datetime(days_offset=1)
            self.display_message(f"AI: The date and time for tomorrow is: {future_datetime}", user=False)
        elif "yesterday" in message_lower:
            past_datetime = get_current_datetime(days_offset=-1)
            self.display_message(f"AI: The date and time for yesterday was: {past_datetime}", user=False)
        elif "today" in message_lower:
            current_datetime = get_current_datetime()
            self.display_message(f"AI: The current date and time is: {current_datetime}", user=False)
        else:
            async def get_response():
                try:
                    # Initialize a SavedHistory object if not already done
                    if not hasattr(self, 'saved_history'):
                        self.saved_history = SavedHistory(model=self.chat_client.history.model)
                    
                    # Add user's message to the history
                    self.saved_history.add_input(message)
                    
                    # Get the response from the AI
                    response = await self.chat_client.ask_question(message)
                    
                    # Add AI's response to the history
                    self.saved_history.add_answer(response)
                    
                    # Display the response
                    self.display_message(f"AI: {response}", user=False)
                    
                    # Optionally, save the history after each response
                    self.saved_history.save()

                except DuckChatException as e:
                    self.display_message(f"Error: {str(e)}", user=False)

            threading.Thread(target=lambda: asyncio.run(get_response())).start()

    def on_stop(self):
        # This method is called when the application is closed.
        if self.chat_client:
            self.loop.run_until_complete(self.chat_client.close_session())  # Close the session asynchronously

        self.loop.close()

if __name__ == "__main__":
    ChatApp().run()
