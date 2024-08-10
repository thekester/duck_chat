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
import asyncio
import threading
from .api import DuckChat, DuckChatException
from .models import ModelType

class ChatApp(App):
    def build(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.chat_client = None

        self.layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Model selection dropdown
        self.model_selector = Spinner(
            text='Select Model',
            values=[model.value for model in ModelType],
            size_hint=(None, None),
            size=(300, 44),  # Adjusted width to 300
            pos_hint={'center_x': 0.5},  # Centered horizontally
        )
        self.layout.add_widget(self.model_selector)

        # Chat display area (inside a scroll view)
        self.chat_display_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=10)
        self.chat_display_layout.bind(minimum_height=self.chat_display_layout.setter('height'))

        self.chat_display = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.chat_display.add_widget(self.chat_display_layout)

        self.layout.add_widget(self.chat_display)

        # User input area
        input_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)

        self.user_input = TextInput(size_hint_y=None, height=44, multiline=False)
        input_layout.add_widget(self.user_input)

        # Send button with a specific size
        self.send_button = Button(
            background_normal='images/send_icon.png',
            size_hint=(None, None),
            size=(46, 37)
        )
        self.send_button.bind(on_press=self.send_message)
        input_layout.add_widget(self.send_button)

        self.layout.add_widget(input_layout)

        return self.layout

    def send_message(self, instance):
        if not self.chat_client:
            self.initialize_chat_client()

        message = self.user_input.text
        if message.strip():
            self.display_message(f"You: {message}", user=True)
            self.user_input.text = ""
            self.handle_chat_response(message)

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
            message_layout.add_widget(Image(source='images/human.png', size_hint=(None, None), size=(25, 27)))
        else:
            message_layout.add_widget(Image(source='images/aichatbot25x26.png', size_hint=(None, None), size=(44, 44)))
            message_layout.add_widget(label)
            message_layout.add_widget(Widget())  # Empty space on the right for bot messages

        # Set the size of the message_layout to ensure it fits the content properly
        message_layout.height = label.height + 20  # Adding padding to prevent overlap

        self.chat_display_layout.add_widget(message_layout)
        self.chat_display_layout.height += message_layout.height  # Increase layout height
        self.chat_display.scroll_to(message_layout)


    def initialize_chat_client(self):
        selected_model = self.model_selector.text
        model_type = ModelType(selected_model)
        self.chat_client = DuckChat(model=model_type)

    def handle_chat_response(self, message):
        async def get_response():
            try:
                await self.chat_client.init_session()
                response = await self.chat_client.ask_question(message)
                self.display_message(f"AI: {response}", user=False)
            except DuckChatException as e:
                self.display_message(f"Error: {str(e)}", user=False)

        threading.Thread(target=lambda: self.loop.run_until_complete(get_response())).start()

if __name__ == "__main__":
    ChatApp().run()
