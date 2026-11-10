import httpx
from backend.app.ai.interfaces import TranslationProvider
from backend.app.core.errors import ServiceError
from backend.app.core.security import decrypt


class HTTPTranslationProvider(TranslationProvider):
    def __init__(self, spec, provider):
        self.spec, self.provider = spec, provider

    def translate(self, text, source, target, beams=4):
        data = self.provider.data
        headers = (
            {"Authorization": "Bearer " + decrypt(self.provider.secret)}
            if self.provider.secret
            else {}
        )
        if data["provider_type"] == "openai_compatible":
            route = "/chat/completions"
            body = {
                "model": self.spec["model_id"] or data["model_name"],
                "messages": [
                    {
                        "role": "system",
                        "content": f"Translate from {source['name']} to {target['name']}. Return only the translation.",
                    },
                    {"role": "user", "content": text},
                ],
                "temperature": 0,
            }
        else:
            route = "/translate"
            body = {
                "text": text,
                "source": source["iso"],
                "target": target["iso"],
                "model": self.spec["model_id"],
            }
        with httpx.Client(
            timeout=data["timeout"], follow_redirects=False, trust_env=False
        ) as client:
            response = client.post(
                data["base_url"].rstrip("/") + route, json=body, headers=headers
            )
            response.raise_for_status()
            result = response.json()
        output = (
            result["choices"][0]["message"]["content"]
            if data["provider_type"] == "openai_compatible"
            else result["translated_text"]
        )
        if not isinstance(output, str) or not output.strip() or len(output) > 20000:
            raise ServiceError(
                "External translation provider returned an invalid response."
            )
        return output
