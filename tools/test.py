from dotenv import load_dotenv
import os

load_dotenv(override=True)

print("OPENAI_API_KEY 来自 .env？", "dBkYuyC8" in os.getenv("OPENAI_API_KEY", ""))
print("TAVILY_API_KEY 来自 .env？", "ZKRYTdAUn" in os.getenv("TAVILY_API_KEY", ""))