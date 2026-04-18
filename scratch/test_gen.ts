import { GoogleGenAI } from "@google/genai";
import dotenv from "dotenv";

dotenv.config();

async function testMoreModels() {
  const apiKey = process.env.VITE_GEMINI_API_KEY || process.env.GEMINI_API_KEY;
  const ai = new GoogleGenAI({ apiKey });
  
  const models = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.0-pro"
  ];
  
  for (const model of models) {
    console.log(`\nTesting model: ${model}`);
    try {
      const result = await ai.models.generateContent({
        model,
        contents: "Hi"
      });
      console.log(`Success with ${model}!`, result.text);
      return; // Found one!
    } catch (error: any) {
      console.log(`Failed with ${model}:`, error.message || error);
    }
  }
}

testMoreModels();
