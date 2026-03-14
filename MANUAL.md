# DEPARTMENT OF TRUTH v5.0: OPERATING MANUAL

You did not install a standard chatbot. Standard AI is a yes-man programmed to agree with your flawed ideas. The Department of Truth is an adversarial engine. It is designed to audit logic, block buzzwords, and force you to defend your strategy with actual data. 

Here is how to operate the system.

## 1. THE INTERFACE & CHAT MECHANICS

### The Bias Interceptor
When you type an idea into the chat, it does not go straight to the main AI. It hits the Bias Interceptor first. 
* If your input is vague, lazy, or relies on massive unverified assumptions, the Interceptor will reject it. 
* You will get a red error box telling you why your logic failed. 
* **The Fix:** Rewrite your input using hard numbers, specific target audiences, and actual constraints.

### Truth Pinning & Memory
Standard AI forgets things as the conversation gets longer. This system uses a rigid state-memory. Under every AI response, you will see action buttons:
* **Pin Truth:** If the AI generates a solid constraint (e.g., "Budget is capped at $500"), pin it. It will turn yellow. This forces the AI to remember this rule for the rest of the session.
* **Pin Assumption:** If the AI guesses something (e.g., "Users will probably want a mobile app"), pin it as an assumption. It turns red. The system is programmed to aggressively attack red assumptions until you provide data to prove them.
* **Make Permanent (Global Truth):** This saves the rule across *all* future sessions. Use this for immutable facts like your company name or permanent budget limits.

### Branching (Forking)
If you reach a crossroads in your strategy and want to explore two different paths without ruining your current chat, click **Fork**. It splits the timeline. You can now explore the new idea safely. 

---

## 2. THE STRATEGIC ACTIONS (BOTTOM BUTTONS)

Once you have built up a conversation, do not just keep chatting. Use the strategic actions at the bottom of the screen to process the data.

* **Roundtable Audit:** Triggers three distinct personas (Strategist, User Advocate, UX Architect) to attack your current strategy simultaneously. 
* **Extract New Ideas:** Forces the AI to identify three highly viable business models or product applications you are ignoring. It is explicitly blocked from hallucinating new capital or magic technology.
* **Compile Artifact:** Takes the messy, scattered chat log and converts it into a clean, professional markdown document: a PRD, a Go-to-Market Strategy, or an Executive Summary. 
* **Execute Merge (In Sidebar):** If you forked a session and now have two good files, select them both here. A "Master Arbitrator" model will read both branches, reconcile the conflicts, and generate a unified master strategy.

---

## 3. THE SIDEBAR & UPLOADS

### Semantic Indexing (RAG)
You can upload PDFs, TXTs, or CSVs. The system will slice the document into nodes and index them. 
* When you ask a question, the engine will only pull answers from your uploaded document. 
* **Limit:** Keep files under 10MB. If you upload massive documents, the local memory will max out and the app will crash. 

### Custom Lenses (Personas)
You can select different lenses from the dropdown (e.g., Technical Lead, Devil's Advocate). If you need a specific expert, open the sidebar and create a Custom Lens. Define their role, set their temperature (0.0 is robotic/factual, 1.0 is creative), and lock it in.

---

## 4. THE ENGINE ROOM (HACKING THE FILES)

The power of a local install is that you control the rules. Open the app folder and edit these text files to change how the system behaves.

* **`strict_rules.txt`**: This is the master rulebook. If you hate specific buzzwords, open this file and add them to the `FORBIDDEN WORDS:` list. If the AI tries to use them, the internal auditor will kill the response and force it to try again.
* **`interceptor_rules.txt`**: This controls the Gatekeeper that judges *your* inputs. Edit this to make it more brutal or more forgiving.
* **`config.json`**: This holds your API key. It also dictates the "Background Model." Default is `gemini-3-flash` because it is fast. Do not change it to "pro" unless you are on a paid tier, or you will burn your quota instantly.

---

## 5. QUOTAS & TROUBLESHOOTING

Google provides 1,500 free requests per day. The sidebar tracks your exact usage, token count, and what the monetary cost *would* be.

* **The Input Field Disappeared:** You hit your daily limit. The system enforces a hard stop to protect you from getting billed. Come back tomorrow.
* **"Rate limit hit. Retrying in 5s...":** The Free Tier only allows 15 requests per minute. If you click buttons too fast, Google blocks you. The app will automatically wait and try again. Just let it sit.
* **The AI failed after 3 attempts:** You likely triggered the "Hype Meter." If the AI generates text with too many words and not enough hard data points, the system rejects it. If it fails three times, you need to write a more specific prompt.