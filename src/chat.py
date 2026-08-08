import json
import os
import sys
from PyQt6.QtCore import QCoreApplication, QUrl
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


class ChatClient:
    def __init__(self, base_url, api_key, model_id, system_instructions):
        # 1. Initialize the network manager
        self.manager = QNetworkAccessManager()

        # Keep a reference to prevent the reply object from being garbage collected
        self.reply = None
        self.base_url = base_url
        self.api_key = api_key
        self.model_id = model_id
        self.system_instructions = system_instructions

    def send_request(self, content):
        url = QUrl(self.base_url)
        request = QNetworkRequest(url)

        # 2. Set headers
        request.setHeader(
            QNetworkRequest.KnownHeaders.UserAgentHeader, "PyQt6Client/1.0"
        )
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"
        )
        request.setRawHeader(b"Authorization", f"Bearer {self.api_key}".encode())

        # 3. Create payload
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": self.system_instructions},
                {"role": "user", "content": content},
            ],
        }
        byte_data = json.dumps(payload).encode("utf-8")

        # 4. Return request and data for caller to post
        return request, byte_data

    def handle_response(self):
        # 5. Check for network errors
        if self.reply.error() != QNetworkReply.NetworkError.NoError:
            print(f"Network Error: {self.reply.errorString()}")
            self.reply.deleteLater()
            QCoreApplication.quit()
            return

        # 6. Read raw bytes and convert to string
        raw_bytes = self.reply.readAll()
        response_text = str(raw_bytes, encoding="utf-8")

        try:
            # 7. Parse JSON structure
            response_json = json.loads(response_text)

            # Extract the content from the typical OpenAI/Groq response format
            answer = response_json["choices"][0]["message"]["content"]
            print(f"\nGroq Response:\n{answer}")

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Failed to parse API response. Error: {e}")
            print(f"Raw Output: {response_text}")

        # Clean up reply memory and exit demo app
        self.reply.deleteLater()
        QCoreApplication.quit()


# Execution entry point
if __name__ == "__main__":
    app = QCoreApplication(sys.argv)
    client = ChatClient(
        base_url=os.getenv("BASE_URL"),
        api_key=os.getenv("API_KEY"),
        model_id=os.getenv("MODEL_ID"),
        system_instructions=os.getenv("SYSTEM_INSTRUCTIONS"),
    )
    client.send_request("Hello")
    sys.exit(app.exec())
