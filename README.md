# ✉️ QA Feedback Email Generator

A privacy-first, automated Quality Assurance feedback email generator. Ingests Excel QA reports, consolidates multiple audited calls per agent into a single direct email, enforces strict zero-verbosity formatting, and leverages dynamic free AI model discovery with zero-error failover.

## 🚀 How to Deploy on Streamlit Community Cloud (Free)

1. Go to [share.streamlit.io](https://share.streamlit.io) and log in with your **GitHub** account.
2. Click **"New app"**.
3. Select your repository, set the branch to `main`, and set the **Main file path** to `app.py`.
4. (Optional) Under **Advanced Settings** -> **Secrets**, you can pre-fill your API keys:
   ```toml
   openrouter_api_key = "your_key_here"
   groq_api_key = "your_key_here"
   current_week = "Week 30"
