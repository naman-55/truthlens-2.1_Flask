import { GoogleGenAI } from "@google/genai";
import dotenv from "dotenv";

dotenv.config();

async function listModels() {
  const apiKey = process.env.VITE_GEMINI_API_KEY || process.env.GEMINI_API_KEY;
  const ai = new GoogleGenAI({ apiKey });
  
  try {
    const response = await ai.models.list();
    console.log("Keys in response:", Object.keys(response));
    // Usually in this SDK, list() returns a list of model objects
    for await (const model of response) {
       console.log(model.name);
    }
  } catch (error) {
    console.error("Error listing models:", error);
  }
}

listModels();
