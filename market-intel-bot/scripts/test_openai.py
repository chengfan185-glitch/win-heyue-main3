import os

def main():
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise SystemExit("OPENAI_API_KEY is missing")

    try:
        from openai import OpenAI
    except Exception as e:
        raise SystemExit(f"openai sdk not installed or import failed: {e}")

    client = OpenAI(api_key=key)

    # 只做最小调用，验证能否通
    r = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input="ping",
        max_output_tokens=10,
    )
    print("ok:", r.output_text)

if __name__ == "__main__":
    main()
