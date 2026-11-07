"""llama.cpp native API: render once, count once, submit those exact token IDs."""
import json
import re
import threading
import httpx
from .prompts import CONTEXT_SIZE, OUTPUT_TOKENS, SAFETY_TOKENS


class ReplyError(ValueError):
    pass


class ModelError(RuntimeError):
    pass


def parse_reply(raw):
    if not isinstance(raw, str) or len(raw) > 64000:
        raise ReplyError('Invalid or oversized model reply')
    text = raw.strip()
    fenced = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text, parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    except (ValueError, TypeError) as e:
        raise ReplyError('Model returned incomplete or invalid JSON') from e
    if not isinstance(value, dict):
        raise ReplyError('Model reply must be a JSON object')
    return value


class LocalModel:
    def __init__(self, port=8091, timeout=180):
        self.base = f'http://127.0.0.1:{int(port)}'
        self.client = httpx.Client(base_url=self.base, timeout=httpx.Timeout(timeout, connect=5), trust_env=False)
        self.lock = threading.Lock()

    def post(self, path, payload):
        try:
            response = self.client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ModelError(f'Local model request failed ({type(e).__name__}); check runtime/model.stderr.log') from e

    def health(self):
        try:
            r = self.client.get('/health', timeout=2)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def tokenize(self, text):
        return self.post('/tokenize', {'content':text, 'add_special':False, 'parse_special':True})['tokens']

    def prepare(self, messages):
        rendered = self.post('/apply-template', {'messages':messages, 'add_generation_prompt':True})['prompt']
        return self.tokenize(rendered)

    def complete(self, tokens, schema):
        if len(tokens) + OUTPUT_TOKENS + SAFETY_TOKENS > CONTEXT_SIZE:
            raise ModelError('Token budget exceeded before inference')
        # Single global worker plus lock; a timed-out call cannot create a second slot.
        with self.lock:
            result = self.post('/completion', {
                'prompt':tokens, 'n_predict':OUTPUT_TOKENS, 'temperature':0,
                'seed':42, 'json_schema':schema, 'stream':False, 'cache_prompt':True,
                'stop':['<|im_end|>'],
            })
        if result.get('truncated') or result.get('stopped_limit') or result.get('stop_type') == 'limit':
            raise ReplyError('Model output reached its limit; call remains incomplete')
        predicted = result.get('tokens_predicted', 0)
        if len(tokens) + predicted > CONTEXT_SIZE:
            raise ReplyError('Runtime reported an over-budget reply')
        return result

    def close(self):
        self.client.close()
