# Department of Truth v5.0 (Experimental Interface)

This is a proof-of-concept experiment. Standard consumer LLM interfaces suffer from predictable failure states during complex workflows. They exhibit conversational sycophancy and lose technical constraints due to sliding window context limits.

The project is an experimental interface built to mitigate those specific behaviours. It tests methods for forcing an LLM to maintain strict parameters and attack unverified logic over extended sessions.

## Experimental Mechanics
* **State-Based Memory (Truth Pinning):** Replaces reliance on passive conversational memory. The user extracts structural constraints from the output and pins them. These variables are injected directly into the foundational system instruction on every subsequent API call.
* **Input Interception:** A secondary background model acts as a pre-processing gate. It audits user inputs for unverified assumptions and rejects prompts lacking factual grounding.
* **Vectorized Context Retrieval:** Evaluates local document parsing and embedding generation to index custom knowledge bases without relying on native LLM file handling.
* **Payload Compression:** Tests an automated sweeping function that condenses raw chat logs into a strict data ledger to optimize token consumption.
* **Asymmetric Persona Deployment:** Tests the efficacy of using aggressively scoped system instructions to force the LLM to identify flaws rather than validate user input.
* **State Synthesis:** Explores methods for taking two diverging conversational logs to extract the core data ledgers and merge them into a single strategic artifact.
* **Token Arbitration:** Implements local ledger systems to track API calls and token volume to prevent budget overrun during testing.

## Customization & Modular Logic
The engine is designed for user manipulation. You can overwrite the core behavioural logic to suit specific project goals.
* **Global Constraints:** Edit `strict_rules.txt` to alter the master system instructions and define your own forbidden vocabulary.
* **Pre-Processing Gatekeeper:** Edit `interceptor_rules.txt` to adjust the strictness and rejection criteria of the input audit model.
* **Strategic Lenses:** Modify the base personas directly within the Python script or generate temporary custom lenses via the application interface.

## Local Deployment
This script requires a local Python environment. It generates the required `/sessions` and `/logs` directories upon execution.

1. Clone the repository.*
2. Install dependencies: pip install -r requirements.txt
3. Generate a personal Gemini API key from Google AI Studio (start with the Free Tier, and adjust your API limits if Paid Tier!).
4. Create a config.json file in the root directory using this exact structure:
   {"api_key": "YOUR_GEMINI_API_KEY", "background_model": "gemini-3-flash"}
5. Execute the application: streamlit run app.py

**Clone? What?**
If you want to try this and do not know what that means, do this:
* Download the Code: Open your Terminal and execute the clone command using the repository URL: git clone https://github.com/fernandoxx73/department-of-truth.git
* Go to the Directory: Navigate into the newly created folder on your machine by typing: cd department-of-truth
* Back to number 2 above.

---

Am I an experienced developer? Of course not. 
But is my code completely optimized? No. 
But do I wake up every day and try to write the most elegant syntax possible? Also no. 

ENJOY!