# Department of Truth v5.0
A strategic decision engine and cognitive bias interceptor, utilizing the Gemini API to force disciplined product architecture.

## Core Architecture
* **Active Memory:** Bypasses standard conversational amnesia by enforcing a "Truth Pinning" mechanic. Extracted signal is hardcoded into the system instruction per execution, rendering raw chat logs disposable.
* **Cognitive Bias Interceptor:** Inputs are gated by a secondary background model designed to block unverified assumptions, hype, and ungrounded language before processing.
* **Asymmetric Persona Deployment:** Utilizes specialized lenses (e.g., Devil's Advocate, UX Architect) to audit inputs and execute strategic merges on conflicting logic branches.
* **Artifact Generation:** Synthesizes chaotic session data into deployable Product Requirements Documents (PRDs) and Go-to-Market (GTM) strategies.

## Local Deployment
1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `config.json` file in the root directory with the following structure:
   `{"api_key": "YOUR_GEMINI_API_KEY", "background_model": "gemini-3-flash"}`
4. Execute the application: `streamlit run app.py`