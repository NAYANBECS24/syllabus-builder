"""Bounded, non-streaming provider calls for evidence extraction and page vision."""
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class CloudError(RuntimeError):
    pass


def parse_object(content):
    if not isinstance(content, str) or len(content) > MAX_RESPONSE_BYTES:
        raise CloudError('Cloud response was empty or too large')
    content = re.sub(r'^\s*```(?:json)?\s*|\s*```\s*$', '', content.strip(), flags=re.I)
    try:
        result = json.loads(content)
    except (ValueError, RecursionError) as exc:
        raise CloudError('Cloud response was not a complete JSON object') from exc
    if not isinstance(result, dict):
        raise CloudError('Cloud response must be a JSON object')
    return result


class CloudModels:
    def __init__(self, provider='nvidia', model='', api_key='', endpoint='', default_nvidia_key=''):
        self.provider = provider
        self.key = api_key or (default_nvidia_key if provider == 'nvidia' and not endpoint else '')
        self.endpoint = endpoint
        defaults = {'nvidia': 'nvidia/nemotron-3.5-bolt-e4b', 'openai': 'gpt-4o-mini', 'gemini': 'gemini-2.0-flash', 'custom': 'llama3.2'}
        self.model = model or defaults.get(provider, '')
        self.vision_model = os.environ.get('SYLEX_VISION_MODEL', '') or (
            'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning' if provider == 'nvidia' and not endpoint else self.model)

    @property
    def available(self):
        return bool(self.key or self.provider == 'custom')

    def complete(self, system, prompt, timeout, image_bytes=None):
        if not self.available:
            raise CloudError('Cloud credentials are not configured; local extraction remains available')
        model = self.vision_model if image_bytes is not None else self.model
        headers = {'Content-Type': 'application/json'}
        if self.provider == 'gemini':
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model, safe="")}:generateContent'
            headers['x-goog-api-key'] = self.key
            parts = [{'text': prompt}]
            if image_bytes is not None:
                parts.append({'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(image_bytes).decode()}})
            payload = {'systemInstruction': {'parts': [{'text': system}]}, 'contents': [{'parts': parts}],
                       'generationConfig': {'temperature': 0, 'maxOutputTokens': 7000, 'responseMimeType': 'application/json'}}
        else:
            base = self.endpoint or {'nvidia': 'https://integrate.api.nvidia.com/v1', 'openai': 'https://api.openai.com/v1', 'custom': 'http://localhost:11434/v1'}.get(self.provider)
            if not base:
                raise CloudError('Unsupported cloud provider')
            url = base.rstrip('/') + '/chat/completions'
            if self.key:
                headers['Authorization'] = 'Bearer ' + self.key
            content = prompt
            if image_bytes is not None:
                content = [{'type': 'text', 'text': prompt}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(image_bytes).decode()}}]
            payload = {'model': model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': content}],
                       'temperature': 0, 'max_tokens': 7000, 'stream': False}
            if image_bytes is None and self.provider == 'openai':
                payload['response_format'] = {'type': 'json_object'}
        request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=max(.1, timeout)) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise CloudError('Cloud response exceeded the size limit')
            data = json.loads(raw)
            if self.provider == 'gemini':
                candidate = data['candidates'][0]
                if candidate.get('finishReason') not in {None, 'STOP'}:
                    raise CloudError('Cloud output was truncated or blocked')
                text = ''.join(part.get('text', '') for part in candidate['content']['parts'])
            else:
                choice = data['choices'][0]
                if choice.get('finish_reason') not in {None, 'stop'}:
                    raise CloudError('Cloud output was truncated or blocked')
                text = choice['message']['content']
            return parse_object(text), model
        except urllib.error.HTTPError as exc:
            # Do not reflect provider bodies, URLs, headers or credentials to the UI.
            raise CloudError(f'Cloud provider returned HTTP {exc.code}') from None
        except (TimeoutError, OSError) as exc:
            raise CloudError('Cloud provider could not respond within the request deadline') from None
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise CloudError('Cloud provider returned an invalid completion') from None
