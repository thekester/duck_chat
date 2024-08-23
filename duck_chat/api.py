from types import TracebackType
from typing import AsyncGenerator, Self

import aiohttp
import msgspec
from fake_useragent import UserAgent

from .exceptions import (
    ConversationLimitException,
    DuckChatException,
    RatelimitException,
)
from .models import History, ModelType, Message, Role
from .models import SavedHistory
import json
import os
import logging
from uuid import uuid4

class DuckChat:
    
    def __init__(
        self,
        model: ModelType = ModelType.Claude,
        session: aiohttp.ClientSession | None = None,
        user_agent: UserAgent | str = UserAgent(min_version=120.0),
    ) -> None:
        # Configuration de base du logging
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)
        if isinstance(user_agent, str):
            self.user_agent = user_agent
        else:
            self.user_agent = user_agent.random  # type: ignore

        self._session = session or aiohttp.ClientSession(
            headers={
                "Host": "duckduckgo.com",
                "Accept": "text/event-stream",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://duckduckgo.com/",
                "User-Agent": self.user_agent,
                "DNT": "1",
                "Sec-GPC": "1",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "TE": "trailers",
            }
        )
        self.vqd: list[str] = []
        self.history = History(model=model, messages=[])  # Historique de la conversation actuelle
        self.saved_history = SavedHistory(model=self.history.model)  # Initialisation unique

        self.__encoder = msgspec.json.Encoder()
        self.__decoder = msgspec.json.Decoder()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self._session.__aexit__(exc_type, exc_value, traceback)

    async def get_vqd(self) -> None:
        """Get new x-vqd-4 token"""
        async with self._session.get(
            "https://duckduckgo.com/duckchat/v1/status", headers={"x-vqd-accept": "1"}
        ) as response:
            if response.status == 429:
                res = await response.read()
                try:
                    err_message = self.__decoder.decode(res).get("type", "")
                except Exception:
                    raise DuckChatException(res.decode())
                else:
                    raise RatelimitException(err_message)
            if "x-vqd-4" in response.headers:
                self.vqd.append(response.headers["x-vqd-4"])
            else:
                raise DuckChatException("No x-vqd-4")

    async def get_answer(self) -> str:
        """Get message answer from chatbot"""
        # Log the request data before sending
        self.logger.debug(f"Sending request with history: {self.history}")

        async with self._session.post(
            "https://duckduckgo.com/duckchat/v1/chat",
            headers={
                "Content-Type": "application/json",
                "x-vqd-4": self.vqd[-1],
            },
            data=self.__encoder.encode(self.history),
        ) as response:
            # Log the status code of the response
            self.logger.debug(f"Response status: {response.status}")
            
            res = await response.read()
            
            # Log the raw response content
            self.logger.debug(f"Raw response content: {res.decode()}")
            
            if response.status == 429:
                self.logger.error("Rate limit exceeded")
                raise RatelimitException(res.decode())
            
            try:
                data = self.__decoder.decode(
                    b"["
                    + b",".join(
                        res.lstrip(b"data: ").rstrip(b"\n\ndata: [DONE][LIMIT_CONVERSATION]\n").split(b"\n\ndata: ")
                    )
                    + b"]"
                )
            except Exception as e:
                self.logger.error(f"Failed to decode response: {str(e)}")
                raise DuckChatException(f"Couldn't parse body={res.decode()}")
            
            message = []
            for x in data:
                if x.get("action") == "error":
                    err_message = x.get("type", "") or str(x)
                    if x.get("status") == 429:
                        if err_message == "ERR_CONVERSATION_LIMIT":
                            self.logger.error("Conversation limit reached")
                            raise ConversationLimitException(err_message)
                        self.logger.error("Rate limit error in action error")
                        raise RatelimitException(err_message)
                    self.logger.error(f"Error in response action: {err_message}")
                    raise DuckChatException(err_message)
                message.append(x.get("message", ""))
        
        # Log the final message before returning
        final_message = "".join(message)
        self.logger.debug(f"Final message: {final_message}")

        self.vqd.append(response.headers.get("x-vqd-4", ""))
        return final_message
    
    async def ask_question(self, query: str) -> str:
        if not self.vqd:
            await self.get_vqd()
        self.history.add_input(query)

        if self._session is None:
            raise DuckChatException("Session closed before completing the request.")
        
        message = await self.get_answer()

        self.history.add_answer(message)
        
        # Ajouter la question et la réponse à l'historique sauvegardé
        self.saved_history.add_input(query)
        self.saved_history.add_answer(message)
        
        # Sauvegarder automatiquement après chaque interaction
        self.saved_history.save()

        return message

    async def reask_question(self, num: int) -> str:
        """Get re-answer from chat AI"""

        if num >= len(self.vqd):
            num = len(self.vqd) - 1
        self.vqd = self.vqd[:num]

        if not self.history.messages:
            return ""

        if not self.vqd:
            await self.get_vqd()
            self.history.messages = [self.history.messages[0]]
        else:
            num = min(num, len(self.vqd))
            self.history.messages = self.history.messages[: (num * 2 - 1)]
        message = await self.get_answer()
        self.history.add_answer(message)

        return message

    async def stream_answer(self) -> AsyncGenerator[str, None]:
        """Stream answer from chatbot"""
        async with self._session.post(
            "https://duckduckgo.com/duckchat/v1/chat",
            headers={
                "Content-Type": "application/json",
                "x-vqd-4": self.vqd[-1],
            },
            data=self.__encoder.encode(self.history),
        ) as response:
            if response.status == 429:
                raise RatelimitException(await response.text())
            try:
                async for line in response.content:
                    if line.startswith(b"data: "):
                        chunk = line[6:]
                        if chunk.startswith(b"[DONE]"):
                            break
                        try:
                            data = self.__decoder.decode(chunk)
                            if "message" in data and data["message"]:
                                yield data["message"]
                        except Exception:
                            raise DuckChatException(f"Couldn't parse body={chunk.decode()}")
            except Exception as e:
                raise DuckChatException(f"Error while streaming data: {str(e)}")
        self.vqd.append(response.headers.get("x-vqd-4", ""))

    async def ask_question_stream(self, query: str) -> AsyncGenerator[str, None]:
        """Stream answer from chat AI"""
        if not self.vqd:
            await self.get_vqd()
        self.history.add_input(query)

        message_list = []
        async for message in self.stream_answer():
            yield message
            message_list.append(message)

        self.history.add_answer("".join(message_list))

    async def reask_question_stream(self, num: int) -> AsyncGenerator[str, None]:
        """Stream re-answer from chat AI"""

        if num >= len(self.vqd):
            num = len(self.vqd) - 1
        self.vqd = self.vqd[:num]

        if not self.history.messages:
            raise GeneratorExit("There is no history messages")

        if not self.vqd:
            await self.get_vqd()
            self.history.messages = [self.history.messages[0]]
        else:
            num = min(num, len(self.vqd))
            self.history.messages = self.history.messages[: (num * 2 - 1)]

        message_list = []
        async for message in self.stream_answer():
            yield message
            message_list.append(message)

        self.history.add_answer("".join(message_list))

    def save_history(self) -> None:
        """Save the current conversation history to a file."""
        saved_history = SavedHistory(model=self.history.model, messages=self.history.messages)
        saved_history.save()
        print(f"History saved with ID: {saved_history.id}")


    @staticmethod
    def load_history(history_id: str) -> History:
        """Load a conversation history from a file."""
        file_path = f"history_{history_id}.json"
        if not os.path.exists(file_path):
            raise DuckChatException(f"No history found for ID {history_id}")
        
        with open(file_path, 'r') as f:
            history_data = json.load(f)
        
        return History(
            model=ModelType(history_data['model']),
            messages=[Message(Role(msg['role']), msg['content']) for msg in history_data['messages']]
        )
        
    async def close_session(self):
        """Close the session and save the final history."""
        # Sauvegarde finale de l'historique avant de fermer la session
        self.saved_history.save()
        
        if self._session is not None:
            await self._session.close()
            self._session = None  # Reset the session to None after closin
