"""Backend adapters. No document bodies or credentials in telemetry."""

import threading
import time
from datetime import datetime, timezone
from functools import lru_cache

import httpx
from pydantic import ValidationError

from .config import api_key
from .model import LocalModel, ModelError


@lru_cache(maxsize=2)
def limiter(concurrency):
    return threading.BoundedSemaphore(concurrency)


class CompatibleModel(LocalModel):
    def __init__(self, settings, transport=None):
        super().__init__(settings)
        self.transport = transport
        self._info = None

    def client(self):
        return httpx.Client(
            base_url=self.settings.base_url.rstrip("/") + "/",
            timeout=self.settings.timeout,
            trust_env=False,
            follow_redirects=False,
            transport=self.transport,
        )

    def info(self):
        if self._info is not None:
            return self._info
        if self.settings.provider != "openrouter":
            self._info = {
                "installed": {"name": self.settings.model},
                "provider": self.settings.provider,
                "endpoint": self.settings.base_url,
                "capabilities": "operator-configured",
            }
            return self._info
        try:
            with self.client() as client:
                response = client.get("models/" + self.settings.model + "/endpoints")
                response.raise_for_status()
                endpoints = response.json()["data"]["endpoints"]
                models = client.get("models")
                models.raise_for_status()
                model = next(m for m in models.json()["data"] if m["id"] == self.settings.model)
            endpoint = next(
                e for e in endpoints if e["tag"] == self.settings.endpoint and e["status"] == 0
            )
            if not {"structured_outputs", "response_format"}.issubset(
                endpoint["supported_parameters"]
            ):
                raise ModelError("Το επιλεγμένο endpoint δεν υποστηρίζει JSON Schema.")
            reasoning = model.get("reasoning", {})
            if not self.settings.reasoning_enabled and reasoning.get("mandatory"):
                raise ModelError(
                    "Το επιλεγμένο μοντέλο απαιτεί reasoning. Αλλάξτε ρητά τη ρύθμιση πριν από νέα αξιολόγηση."
                )
            self._info = {
                "installed": {"name": self.settings.model},
                "endpoint": endpoint,
                "reasoning_capabilities": reasoning,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "excluded_variants": [
                    e["tag"] for e in endpoints if e["tag"].startswith(self.settings.endpoint + "/")
                ],
            }
            return self._info
        except (httpx.HTTPError, ValueError, KeyError, StopIteration):
            raise ModelError(
                "Αποτυχία επαλήθευσης διαθεσιμότητας του σταθερού endpoint. Δεν έγινε fallback."
            ) from None

    def generate(self, prompt, schema):
        if not self.fits(prompt, schema):
            raise ModelError("Το context υπερβαίνει το επιλεγμένο όριο.")
        secret = api_key(self.settings.provider)
        if self.settings.provider == "openrouter" and (
            not secret or secret.startswith("your-") or secret.startswith("<")
        ):
            raise ModelError(
                "Λείπει το API key. Εκκινήστε την εφαρμογή με --live και εισαγάγετε το δικό σας κλειδί."
            )
        info = self.info()
        messages = self.messages(prompt, schema)
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "stream": False,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.num_predict,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            },
        }
        if self.settings.provider == "openrouter":
            payload["provider"] = {
                "only": [self.settings.endpoint],
                "order": [self.settings.endpoint],
                "ignore": info["excluded_variants"],
                "allow_fallbacks": False,
                "require_parameters": True,
            }
            if "reasoning" in info["endpoint"]["supported_parameters"]:
                payload["reasoning"] = {"enabled": self.settings.reasoning_enabled}
            elif self.settings.reasoning_enabled:
                raise ModelError(
                    "Το επιλεγμένο endpoint δεν υποστηρίζει τη ζητημένη παράμετρο reasoning."
                )
        headers = {"Authorization": "Bearer " + secret} if secret else {}
        remaining_retries = self.settings.retries
        # Bound concurrent provider calls across model instances in this process.
        with limiter(self.settings.concurrency):
            for repair in range(2):
                while True:
                    start = time.perf_counter()
                    event = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "model": self.settings.model,
                        "gateway": self.settings.provider,
                        "endpoint_requested": self.settings.endpoint,
                        "prompt_version": self.settings.prompt_version,
                        "operation": schema.__name__,
                        "reasoning_requested": payload.get("reasoning"),
                        "max_output_tokens": self.settings.num_predict,
                        "schema_repair": repair,
                        "mode": "live",
                    }
                    try:
                        with self.client() as client:
                            response = client.post(
                                "chat/completions", json=payload, headers=headers
                            )
                        event["http_status"] = response.status_code
                        if response.status_code >= 400:
                            transient = response.status_code in {408, 429, 500, 502, 503, 504}
                            event["error"] = "transient_http" if transient else "http_error"
                            if transient and remaining_retries:
                                remaining_retries -= 1
                                time.sleep(2 ** (self.settings.retries - remaining_retries - 1))
                                continue
                            explanations = {
                                401: "Το API key απορρίφθηκε.",
                                402: "Δεν υπάρχει διαθέσιμο υπόλοιπο API.",
                                403: "Η πρόσβαση απαγορεύτηκε.",
                                404: "Το σταθερό endpoint δεν είναι διαθέσιμο.",
                                429: "Υπέρβαση ορίου κλήσεων.",
                            }
                            raise ModelError(
                                f"Σφάλμα LLM API (HTTP {response.status_code}). "
                                + explanations.get(response.status_code, "Επαναλάβετε αργότερα.")
                            )
                        try:
                            result = response.json()
                        except ValueError:
                            result = {}
                        if not isinstance(result, dict):
                            event["error"] = "invalid_api_response"
                            raise ModelError("Ο provider επέστρεψε μη έγκυρη δομή απόκρισης API.")
                        usage = result.get("usage") or {}
                        if not isinstance(usage, dict):
                            usage = {}
                        event.update({k: result.get(k) for k in ("id", "model", "provider")})
                        event.update(
                            prompt_tokens=usage.get("prompt_tokens"),
                            completion_tokens=usage.get("completion_tokens"),
                            total_tokens=usage.get("total_tokens"),
                            cost_usd=usage.get("cost"),
                            reasoning_tokens=(usage.get("completion_tokens_details") or {}).get(
                                "reasoning_tokens"
                            )
                            if isinstance(usage.get("completion_tokens_details") or {}, dict)
                            else None,
                        )
                        if result.get("error"):
                            event["error"] = "provider_error"
                            raise ModelError(
                                "Ο provider επέστρεψε σφάλμα επεξεργασίας. Δεν έγινε fallback."
                            )
                        if result.get("model") != self.settings.model or (
                            self.settings.provider == "openrouter"
                            and result.get("provider") != info["endpoint"]["provider_name"]
                        ):
                            event["error"] = "route_mismatch"
                            raise ModelError(
                                "Η απόκριση δεν επιβεβαιώνει το κλειδωμένο μοντέλο/provider."
                            )
                        choices = result.get("choices")
                        if (
                            not isinstance(choices, list)
                            or not choices
                            or not isinstance(choices[0], dict)
                        ):
                            event["error"] = "invalid_api_response"
                            raise ModelError("Ο provider δεν επέστρεψε έγκυρη απάντηση API.")
                        choice = choices[0]
                        event["finish_reason"] = choice.get("finish_reason")
                        if choice.get("finish_reason") == "length":
                            event["error"] = "truncated"
                            raise ModelError(
                                "Η απάντηση κόπηκε στο όριο output tokens. Η εξαγωγή δεν ολοκληρώθηκε."
                            )
                        if choice.get("finish_reason") not in {"stop"}:
                            event["error"] = "incomplete"
                            raise ModelError("Το μοντέλο δεν ολοκλήρωσε κανονικά την απάντηση.")
                        try:
                            parsed = schema.model_validate_json(
                                choice["message"]["content"], strict=True
                            )
                            event["validated"] = True
                            return parsed
                        except (ValidationError, KeyError, ValueError, TypeError):
                            event["error"] = "invalid_schema"
                            if repair:
                                raise ModelError(
                                    "Σφάλμα επεξεργασίας: μη έγκυρο JSON/schema και μετά τη μία προσπάθεια διόρθωσης."
                                ) from None
                            # Do not forward unvalidated model text or exception strings containing source text.
                            messages.append(
                                {
                                    "role": "user",
                                    "content": "Η προηγούμενη απόκριση απέτυχε στο JSON/schema. Επανέλαβε από τις ίδιες πηγές: ακριβείς τύποι, όλα τα απαιτούμενα πεδία, χωρίς επιπλέον πεδία. Μόνο JSON.",
                                }
                            )
                            break
                    except (httpx.TimeoutException, httpx.NetworkError):
                        event["error"] = "network_or_timeout"
                        if remaining_retries:
                            remaining_retries -= 1
                            time.sleep(2 ** (self.settings.retries - remaining_retries - 1))
                            continue
                        raise ModelError(
                            "Timeout ή σφάλμα σύνδεσης LLM API μετά τις περιορισμένες επαναλήψεις."
                        ) from None
                    except httpx.HTTPError:
                        event["error"] = "transport_error"
                        raise ModelError("Σφάλμα μεταφοράς LLM API. Ελέγξτε τη σύνδεση.") from None
                    finally:
                        event["seconds"] = time.perf_counter() - start
                        self.calls.append(event)


def create_model(settings):
    if settings.execution_mode == "replay":
        raise ModelError(
            "REPLAY: χρησιμοποιήστε αποθηκευμένη εκτέλεση. Οι κλήσεις LLM είναι απενεργοποιημένες."
        )
    return LocalModel(settings) if settings.provider == "ollama" else CompatibleModel(settings)
