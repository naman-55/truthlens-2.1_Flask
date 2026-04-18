import { GoogleGenAI } from "@google/genai";
import dotenv from "dotenv";

dotenv.config();

async function testV1() {
  const apiKey = process.env.VITE_GEMINI_API_KEY || process.env.GEMINI_API_KEY;
  // @ts-ignore - testing if constructor accepts apiVersion
  const ai = new GoogleGenAI({ apiKey, apiVersion: "v1" });
  
  try {
    const result = await ai.models.generateContent({
      model: "gemini-1.5-flash",
      contents: "Hi"
    });
    console.log("Success with v1!", result.text);
  } catch (error: any) {
    console.log("Failed with v1:", error.message || error);
  }
}

testV1();
