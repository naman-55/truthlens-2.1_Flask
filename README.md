# 🔍 TruthLens - AI-Powered Fact Checker & Digital Forensics

TruthLens is a modern, AI-driven web application designed to combat misinformation. It analyzes text claims, news snippets, and images to determine their authenticity, factual accuracy, and whether they appear to be AI-generated or manipulated.

## ✨ Features

*   **📝 Text Verification:** Paste any news headline, claim, or text snippet. The AI acts as an investigative journalist to fact-check the content and provide a detailed analysis.
*   **🖼️ Image Forensics:** Upload screenshots or photographs. The app extracts claims from the image and performs visual forensics to detect signs of digital manipulation or AI generation.
*   **⚡ Lightning Fast AI:** Powered by **Google Gemini API** with integrated Google Search grounding.
*   **🔄 Hybrid Fallback:** Smart fallback system that automatically switches to non-grounded search on quota limits, and transitions to **OpenAI (GPT-4o)** if Gemini is unavailable.
*   **🕒 Scan History:** Automatically saves your recent verifications to your browser's local storage. Access them anytime via the History sidebar.
*   **🗑️ History Management:** Easily clear your entire scan history with a custom, secure confirmation modal (bypassing restrictive browser iframes).
*   **🎨 Immersive UI/UX:** Features a dark-themed, modern interface with floating data particles, a custom lag-free glowing cursor, and smooth animations powered by Framer Motion.

## 🛠️ Tech Stack

*   **Frontend Framework:** React 18+ with TypeScript
*   **Build Tool:** Vite
*   **Styling:** Tailwind CSS
*   **Animations:** `motion/react` (Framer Motion)
*   **Icons:** `lucide-react`
*   **AI Integration:** `@google/genai` (Google Gemini) & `openai` (GPT-4o)

## 🧠 How It Works (Under the Hood)

1.  **Input Handling:** The user provides text, an image, or both via the UI. Images are converted to Base64 format for processing.
2.  **Prompt Engineering:** The app constructs a highly specific system prompt instructing the AI to act as a fact-checker and return its findings in a strict JSON format.
3.  **AI Processing (Gemini):**
    *   The app calls Google Gemini using `@google/genai`.
    *   It discovers available `generateContent` models with ListModels, then prefers current flash models and only falls back to supported alternatives.
    *   **Smart Fallback:** If grounded search hits quota limits, it tries again without grounding.
    *   **OpenAI Backup:** If Gemini fails entirely, it attempts verification via the OpenAI API (if `VITE_OPENAI_API_KEY` is set).
4.  **Structured Output:** The AI returns a JSON object containing:
    *   `verdict`: (Real, Fake, Misleading, or Unverified)
    *   `aiProbability`: (0-100 score)
    *   `summary`: A quick 1-2 sentence overview.
    *   `detailedAnalysis`: Bullet points of the deep dive.
    *   `sources`: Credible source links used for verification.
5.  **State Management:** The result is displayed beautifully on the UI and saved to `localStorage` (`truthlens_history`) for future reference.

## 🚀 Local Setup Instructions

Follow these steps to run TruthLens on your local machine:

### 1. Prerequisites
Ensure you have [Node.js](https://nodejs.org/) installed on your system.

### 2. Install Dependencies
Open your terminal, navigate to the project folder, and run:
```bash
npm install
```

### 3. Environment Variables
1. Create a `.env` file in the root directory of the project.
2. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
3. Add your Gemini API key to the `.env` file like this:
```env
VITE_GEMINI_API_KEY=AIza_your_actual_api_key_here
VITE_OPENAI_API_KEY=sk_your_openai_api_key_here  # Optional fallback
```
*(Optional fallback aliases supported: `VITE_API_KEY`, `VITE_API_ID`, `GEMINI_API_KEY`.)**

### 4. Run the Development Server
Start the app by running:
```bash
npm run dev
```
Click the local link provided in the terminal (usually `http://localhost:5173`) to open the app in your browser!

### 5. If You See "quota/rate limit" or "Unverified"
1. Generate a fresh key in Google AI Studio: https://aistudio.google.com/app/apikey
2. Replace key values in your local `.env`.
3. Restart dev server (`npm run dev`).
4. Ensure API key restrictions allow local usage (localhost) and that quota/billing is active.

---
*Built with ❤️ focusing on clean code, smooth animations, and reliable AI integrations.*
