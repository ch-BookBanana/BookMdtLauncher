import os
from openai import OpenAI

client = OpenAI(
    api_key='sk-024a1c0c38494bc7a26b4dc708713c38',
    base_url="https://api.deepseek.com")

response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ],
    stream=False,
    reasoning_effort="high"
    )

print(response.choices[0].message.content)