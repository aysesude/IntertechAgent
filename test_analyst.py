import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator import run_orchestrator  # noqa: E402, I001


async def main():
    # Provide dummy API key if missing
    if not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "sk-dummy"

    user_id = "test_user_id"
    message = "Akbank'ın bilançosu ne anlama geliyor, hisse ucuz mu kaldı?"

    print(f"Soru: {message}")
    print("Orkestratör çalışıyor...\n")

    # Needs to be mocked or run with live MCP server.
    # Since we can't easily mock the MCP server in a simple script here without a lot of setup,
    # we just run the orchestrator up to the intent detection for verification.

    try:
        response = await run_orchestrator(user_id, message)
        print(f"\nFinal Yanıt: {response['final_answer']}")
        print(f"Niyet: {response['intent']}")
    except Exception as e:
        print(f"Hata: {e}")


if __name__ == "__main__":
    asyncio.run(main())
