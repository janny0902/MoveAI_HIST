# Cursor + LiteLLM + Vertex AI (Google free credit)

## Project
- GCP Project ID: `moveai-504907`
- Proxy URL: `http://127.0.0.1:4000/v1`
- Master key: `sk-moveai-local`
- Models: `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash`

## One-time auth
```bat
d:\moveAI\litellm-proxy\reauth-adc.bat
```
Or:
```bat
gcloud auth application-default login
gcloud auth application-default set-quota-project moveai-504907
gcloud config set project moveai-504907
```

Enable **Vertex AI API** on project `moveai-504907` and confirm free credits/billing are on this project.

## Start proxy
`d:\moveAI\litellm-proxy\start-proxy.bat` (keep window open)

## Cursor
- OpenAI API Key: `sk-moveai-local`
- Override OpenAI Base URL: `http://localhost:4000/v1`
- Model: `gemini-2.5-flash` (fallback: `gemini-1.5-flash`)
