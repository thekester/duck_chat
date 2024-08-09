from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.clock import Clock  # Importer Clock pour planifier les mises à jour d'interface
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
            size=(200, 44),
        )
        self.layout.add_widget(self.model_selector)

        # Chat display area (inside a scroll view)
        self.chat_display_layout = GridLayout(cols=1, size_hint_y=None)
        self.chat_display_layout.bind(minimum_height=self.chat_display_layout.setter('height'))

        self.chat_display = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.chat_display.add_widget(self.chat_display_layout)

        self.layout.add_widget(self.chat_display)

        # User input area
        self.user_input = TextInput(size_hint_y=None, height=50, multiline=False)
        self.layout.add_widget(self.user_input)

        # Send button
        self.send_button = Button(text="Send", size_hint_y=None, height=50)
        self.send_button.bind(on_press=self.send_message)
        self.layout.add_widget(self.send_button)

        return self.layout

    def send_message(self, instance):
        if not self.chat_client:
            self.initialize_chat_client()

        message = self.user_input.text
        if message.strip():
            self.display_message(f"You: {message}")
            self.user_input.text = ""
            self.handle_chat_response(message)

    def display_message(self, message):
        # Utiliser Clock.schedule_once pour s'assurer que l'UI est mise à jour depuis le thread principal
        Clock.schedule_once(lambda dt: self._add_message_to_display(message))

    def _add_message_to_display(self, message):
        label = Label(
            text=message,
            size_hint_y=None,
            height=44,
            halign='left',
            valign='middle',
        )
        label.bind(size=lambda *x: label.setter('text_size')(label, label.size))
        self.chat_display_layout.add_widget(label)
        self.chat_display.scroll_to(label)

    def initialize_chat_client(self):
        selected_model = self.model_selector.text
        model_type = ModelType(selected_model)
        self.chat_client = DuckChat(model=model_type)

    def handle_chat_response(self, message):
        async def get_response():
            try:
                await self.chat_client.init_session()
                response = await self.chat_client.ask_question(message)
                self.display_message(f"AI: {response}")
            except DuckChatException as e:
                self.display_message(f"Error: {str(e)}")

        threading.Thread(target=lambda: self.loop.run_until_complete(get_response())).start()

if __name__ == "__main__":
    ChatApp().run()
