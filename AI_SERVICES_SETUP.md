# 🤖 AI Services Setup Guide

Bu rehber, trading bot'unuzda OpenAI, Google Gemini ve DeepSeek AI servislerini nasıl yapılandıracağınızı açıklar.

## 📋 İçindekiler

1. [OpenAI Setup](#openai-setup)
2. [Google Gemini Setup](#google-gemini-setup)
3. [DeepSeek Setup](#deepseek-setup)
4. [Kullanım Örnekleri](#kullanım-örnekleri)

---

## 🔵 OpenAI Setup

### 1. API Key Alma

1. [OpenAI Platform](https://platform.openai.com/) adresine gidin
2. Hesap oluşturun veya giriş yapın
3. **API Keys** bölümüne gidin
4. **Create new secret key** butonuna tıklayın
5. API key'inizi kopyalayın (sadece bir kez gösterilir!)

### 2. Environment Variables

`.env` dosyanıza ekleyin:

```env
OPENAI_API_KEY=sk-your_openai_api_key_here
OPENAI_MODEL=gpt-4-turbo-preview
OPENAI_TEMPERATURE=0.7
OPENAI_MAX_TOKENS=2000
```

### 3. Mevcut Modeller

- `gpt-4` - En güçlü model (pahalı)
- `gpt-4-turbo-preview` - Hızlı ve güçlü (önerilen)
- `gpt-3.5-turbo` - Hızlı ve ekonomik

### 4. Fiyatlandırma

- **GPT-4 Turbo**: ~$0.01 / 1K input tokens, ~$0.03 / 1K output tokens
- **GPT-3.5 Turbo**: ~$0.0005 / 1K input tokens, ~$0.0015 / 1K output tokens

### 5. Rate Limits

- **Free tier**: 3 RPM (requests per minute), 200 RPD (requests per day)
- **Tier 1**: 500 RPM, 10,000 TPM (tokens per minute)

---

## 🟢 Google Gemini Setup

### 1. API Key Alma

1. [Google AI Studio](https://makersuite.google.com/app/apikey) adresine gidin
2. Google hesabınızla giriş yapın
3. **Create API Key** butonuna tıklayın
4. API key'inizi kopyalayın

### 2. Environment Variables

`.env` dosyanıza ekleyin:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-pro
GEMINI_TEMPERATURE=0.7
GEMINI_MAX_OUTPUT_TOKENS=2048
```

### 3. Mevcut Modeller

- `gemini-pro` - Genel amaçlı model (önerilen)
- `gemini-pro-vision` - Görüntü analizi desteği

### 4. Fiyatlandırma

- **Gemini Pro**: Ücretsiz (sınırlı kullanım)
- **Gemini Pro (Paid)**: $0.00025 / 1K characters input, $0.0005 / 1K characters output

### 5. Rate Limits

- **Free tier**: 15 RPM, 1,500 RPD
- **Paid tier**: Daha yüksek limitler

---

## 🟡 DeepSeek Setup

### 1. API Key Alma

1. [DeepSeek Platform](https://platform.deepseek.com/) adresine gidin
2. Hesap oluşturun veya giriş yapın
3. **API Keys** bölümüne gidin
4. Yeni API key oluşturun
5. API key'inizi kopyalayın

### 2. Environment Variables

`.env` dosyanıza ekleyin:

```env
DEEPSEEK_API_KEY=sk-your_deepseek_api_key_here
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TEMPERATURE=0.7
DEEPSEEK_MAX_TOKENS=2000
```

### 3. Mevcut Modeller

- `deepseek-chat` - Genel amaçlı sohbet modeli (önerilen)
- `deepseek-coder` - Kod üretimi için optimize edilmiş

### 4. Fiyatlandırma

- **DeepSeek Chat**: ~$0.00014 / 1K input tokens, ~$0.00028 / 1K output tokens
- **DeepSeek Coder**: ~$0.00055 / 1K input tokens, ~$0.0011 / 1K output tokens

### 5. Rate Limits

- Varsayılan: 100 RPM
- Premium: Daha yüksek limitler

---

## 💻 Kullanım Örnekleri

### Python ile OpenAI Kullanımı

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

response = client.chat.completions.create(
    model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"),
    messages=[
        {"role": "system", "content": "You are a trading bot assistant."},
        {"role": "user", "content": "Analyze BTCUSDT market conditions."}
    ],
    temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
    max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "2000"))
)

print(response.choices[0].message.content)
```

### Python ile Gemini Kullanımı

```python
import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-pro"))

response = model.generate_content(
    "Analyze BTCUSDT market conditions.",
    generation_config={
        "temperature": float(os.getenv("GEMINI_TEMPERATURE", "0.7")),
        "max_output_tokens": int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2048"))
    }
)

print(response.text)
```

### Python ile DeepSeek Kullanımı

```python
import os
from openai import OpenAI

# DeepSeek uses OpenAI-compatible API
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
)

response = client.chat.completions.create(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    messages=[
        {"role": "system", "content": "You are a trading bot assistant."},
        {"role": "user", "content": "Analyze BTCUSDT market conditions."}
    ],
    temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7")),
    max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "2000"))
)

print(response.choices[0].message.content)
```

---

## 🔒 Güvenlik Notları

1. **API Key'leri asla commit etmeyin**
   - `.env` dosyası `.gitignore`'da olmalı
   - API key'leri sadece `.env` dosyasında tutun

2. **Rate Limit Yönetimi**
   - Her servis için rate limit'leri kontrol edin
   - Gerekirse retry logic ekleyin
   - Exponential backoff kullanın

3. **Maliyet Kontrolü**
   - Token kullanımını izleyin
   - Max tokens limitlerini ayarlayın
   - Gereksiz API çağrılarından kaçının

4. **Error Handling**
   - API hatalarını yakalayın
   - Fallback mekanizmaları ekleyin
   - Logging yapın

---

## 📦 Gerekli Paketler

```bash
# OpenAI
pip install openai

# Google Gemini
pip install google-generativeai

# DeepSeek (OpenAI-compatible, same package)
pip install openai
```

---

## 🧪 Test Etme

Her servisi test etmek için:

```python
# test_ai_services.py
import os
from dotenv import load_dotenv

load_dotenv()

# Test OpenAI
if os.getenv("OPENAI_API_KEY"):
    print("✅ OpenAI API key found")
else:
    print("❌ OpenAI API key not found")

# Test Gemini
if os.getenv("GEMINI_API_KEY"):
    print("✅ Gemini API key found")
else:
    print("❌ Gemini API key not found")

# Test DeepSeek
if os.getenv("DEEPSEEK_API_KEY"):
    print("✅ DeepSeek API key found")
else:
    print("❌ DeepSeek API key not found")
```

---

## 📚 Ek Kaynaklar

- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Google Gemini API Documentation](https://ai.google.dev/docs)
- [DeepSeek API Documentation](https://platform.deepseek.com/docs)

---

## ⚠️ Önemli Notlar

1. **İlk kullanımda test edin**: Her servisi küçük bir test ile doğrulayın
2. **Maliyetleri izleyin**: API kullanımınızı düzenli olarak kontrol edin
3. **Rate limit'lere dikkat edin**: Aşırı istek göndermeyin
4. **Error handling ekleyin**: API hatalarını yakalayın ve işleyin
5. **Logging yapın**: Tüm API çağrılarını loglayın

---

**Son Güncelleme**: 2025-01-27
